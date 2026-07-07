"""Εφαρμογή εισαγωγής ωραρίου από staging σε Ergani (WTODaily)."""

from __future__ import annotations

from typing import Any

from flask import current_app

from app.db import cursor
from app.ergani_client import ErganiClient
from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, response_body_text
from app.repo_entities import upsert_employee
from app.repo_schedule_import import (
    get_import_batch,
    list_apply_rows,
    list_import_rows,
    update_batch_status,
    update_import_row_result,
)
from app.routes_wto_daily import (
    _current_schedule_snapshot,
    _persist_local_schedule_after_wto_daily,
    _persist_wto_daily_submit,
    _submit_wto_daily_with_auth_retry,
    record_wto_daily_schedule_audit,
)
from app.schedule_excel_import import summarize_import_rows
from app.today_notify_logic import ergani_date_to_iso
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY, build_wto_daily_payload
from app.work_card_payload import WorkCardPayloadError


def _import_row_to_body(row: dict[str, Any]) -> dict[str, Any]:
    ref_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
    body: dict[str, Any] = {
        "employee_afm": str(row.get("employee_afm") or "").strip(),
        "reference_date": ref_iso,
        "eponymo": str(row.get("eponymo") or "").strip(),
        "onoma": str(row.get("onoma") or "").strip(),
        "comments": "Εισαγωγή εβδομαδιαίου ωραρίου από Excel",
    }
    if str(row.get("import_action") or "") == "rest":
        body["schedule_type"] = "ΑΝ"
        return body

    proposed = row.get("proposed_snapshot") if isinstance(row.get("proposed_snapshot"), list) else []
    intervals = [
        {
            "hour_from": str(item.get("hour_from") or "").strip(),
            "hour_to": str(item.get("hour_to") or "").strip(),
        }
        for item in proposed
        if isinstance(item, dict)
    ]
    body["schedule_type"] = "ΕΡΓ"
    body["intervals"] = intervals
    if len(intervals) == 1:
        body["hour_from"] = intervals[0].get("hour_from")
        body["hour_to"] = intervals[0].get("hour_to")
    return body


def apply_import_row(ctx: dict[str, Any], row: dict[str, Any], bearer: str) -> dict[str, Any]:
    body = _import_row_to_body(row)
    emp_afm = str(body.get("employee_afm") or "").strip()
    ref_date = str(body.get("reference_date") or "").strip()
    last = str(body.get("eponymo") or "").strip()
    first = str(body.get("onoma") or "").strip()
    try:
        payload = build_wto_daily_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            reference_date=ref_date,
            schedule_type=str(body.get("schedule_type") or "ΕΡΓ"),
            hour_from=body.get("hour_from"),
            hour_to=body.get("hour_to"),
            intervals=body.get("intervals") if isinstance(body.get("intervals"), list) else None,
            comments=body.get("comments"),
        )
    except WorkCardPayloadError as ex:
        return {"success": False, "error": str(ex), "http_status": 400}

    work_date_ergani = payload["WTOS"]["WTO"][0]["f_from_date"]
    old_schedule = _current_schedule_snapshot(
        ctx,
        employee_afm=emp_afm,
        work_date_ergani=work_date_ergani,
    )
    client = ErganiClient(ctx.get("api_base_url"))
    resp, parsed, auth_retry = _submit_wto_daily_with_auth_retry(ctx, client, payload, bearer)
    protocol = submit_date = ergani_id = None
    if resp.ok and isinstance(parsed, list) and parsed:
        first_item = parsed[0]
        if isinstance(first_item, dict):
            protocol = first_item.get("protocol")
            submit_date = first_item.get("submitDate")
            raw_id = first_item.get("id")
            ergani_id = str(raw_id).strip() if raw_id is not None else None

    persist_safe(
        _persist_wto_daily_submit,
        str(ctx["employer_afm"]),
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
    )

    local_schedule_updated = False
    if resp.ok:
        with cursor() as cur:
            upsert_employee(cur, emp_afm, last, first)
        local_schedule_updated = _persist_local_schedule_after_wto_daily(
            ctx,
            employee_afm=emp_afm,
            body=body,
            payload=payload,
        )
        record_wto_daily_schedule_audit(
            ctx,
            employee_afm=emp_afm,
            eponymo=last,
            onoma=first,
            work_date_ergani=work_date_ergani,
            body=body,
            old_schedule=old_schedule,
            protocol=protocol,
            ergani_submission_id=ergani_id,
            local_schedule_updated=local_schedule_updated,
            http_status=resp.status_code,
            success=resp.ok,
        )

    err_msg = None
    if not resp.ok:
        if isinstance(parsed, dict):
            err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None
        if not err_msg:
            err_msg = response_body_text(resp)[:500] or "Αποτυχία WTODaily"

    return {
        "success": resp.ok,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "http_status": resp.status_code,
        "local_schedule_updated": local_schedule_updated,
        "auth_retry": auth_retry,
        "error": err_msg,
        "data": parsed,
    }


def confirm_import_batch(ctx: dict[str, Any], batch_id: int) -> dict[str, Any]:
    batch = get_import_batch(batch_id, store_id=int(ctx["id"]))
    if not batch:
        return {"success": False, "error": "Δεν βρέθηκε η εισαγωγή"}
    status = str(batch.get("status") or "")
    if status not in ("preview", "failed"):
        return {"success": False, "error": f"Η εισαγωγή είναι σε κατάσταση «{status}»"}

    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return {"success": False, "error": "Αποτυχία σύνδεσης Ergani API (web user)"}

    rows = list_apply_rows(batch_id)
    if not rows:
        update_batch_status(batch_id, "applied", summary={"applied": 0, "failed": 0, "total": 0})
        return {"success": True, "applied": 0, "failed": 0, "results": []}

    update_batch_status(batch_id, "applying")
    applied = 0
    failed = 0
    results: list[dict[str, Any]] = []

    for row in rows:
        row_id = int(row["id"])
        try:
            result = apply_import_row(ctx, row, bearer)
        except Exception as ex:
            current_app.logger.exception("schedule import apply failed")
            result = {"success": False, "error": str(ex), "http_status": 500}

        ok = bool(result.get("success"))
        if ok:
            applied += 1
            update_import_row_result(
                row_id,
                apply_status="success",
                apply_message="Εφαρμόστηκε στο Ergani",
                ergani_protocol=str(result.get("protocol") or "") or None,
            )
        else:
            failed += 1
            update_import_row_result(
                row_id,
                apply_status="failed",
                apply_message=str(result.get("error") or "Αποτυχία")[:500],
            )
        results.append(
            {
                "row_id": row_id,
                "employee_afm": row.get("employee_afm"),
                "work_date": row.get("work_date"),
                "success": ok,
                "protocol": result.get("protocol"),
                "error": result.get("error"),
            }
        )

    summary = summarize_import_rows(list_import_rows(batch_id))
    summary["applied_ok"] = applied
    summary["applied_failed"] = failed
    final_status = "applied" if failed == 0 else "failed"
    update_batch_status(batch_id, final_status, summary=summary)
    return {
        "success": failed == 0,
        "applied": applied,
        "failed": failed,
        "results": results,
        "summary": summary,
    }
