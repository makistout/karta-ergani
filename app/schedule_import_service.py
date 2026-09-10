"""Εφαρμογή εισαγωγής ωραρίου από staging σε Ergani (WTOWeek ανά εργαζόμενο)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from flask import current_app

from app.audit_log import record_audit_event
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
    record_wto_daily_schedule_audit,
)
from app.routes_wto_week import _persist_submit as _persist_wto_week_submit
from app.schedule_excel_import import summarize_import_rows
from app.schedule_sync import fetch_and_save_schedule_for_ctx
from app.today_notify_logic import ergani_date_to_iso
from app.work_card_payload import WorkCardPayloadError
from app.wto_daily_payload import build_wto_daily_payload
from app.wto_week_payload import SUBMISSION_CODE_WTO_WEEK, build_wto_week_payload


def _import_row_to_body(row: dict[str, Any]) -> dict[str, Any]:
    ref_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
    body: dict[str, Any] = {
        "employee_afm": str(row.get("employee_afm") or "").strip(),
        "reference_date": ref_iso,
        "eponymo": str(row.get("eponymo") or "").strip(),
        "onoma": str(row.get("onoma") or "").strip(),
        "comments": str(row.get("comments") or "").strip()
        or "Εισαγωγή εβδομαδιαίου ωραρίου από Excel",
    }
    if str(row.get("import_action") or "") in ("rest", "absent"):
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


def apply_import_row(
    ctx: dict[str, Any],
    row: dict[str, Any],
    bearer: str,
    *,
    batch_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Μεμονωμένη ημέρα μέσω WTODaily (AI Agent / συμβατότητα)."""
    from app.routes_wto_daily import (
        _persist_wto_daily_submit,
        _submit_wto_daily_with_auth_retry,
    )

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

    err_msg = None
    if not resp.ok:
        if isinstance(parsed, dict):
            err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None
        if not err_msg:
            err_msg = response_body_text(resp)[:500] or "Αποτυχία WTODaily"

    meta = batch_meta if isinstance(batch_meta, dict) else {}
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
        source=str(meta.get("source") or "excel_import"),
        import_batch_id=meta.get("batch_id"),
        import_row_id=row.get("id"),
        original_filename=meta.get("original_filename"),
        week_label=meta.get("week_label"),
        error_message=err_msg,
    )

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


def _ergani_weekday(work_date_ergani: str) -> int:
    """Ergani f_day: 0=Κυριακή … 6=Σάββατο."""
    dt = datetime.strptime(str(work_date_ergani).strip()[:10], "%d/%m/%Y").date()
    return (dt.weekday() + 1) % 7


def _snapshot_to_week_entries(snapshot: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows = [item for item in (snapshot or []) if isinstance(item, dict)]
    if not rows:
        # Χωρίς δηλωμένο ωράριο και χωρίς ΡΕΠΟ → Μη εργασία (όχι Ανάπαυση).
        return [{"type": "ΜΕ"}]
    first = rows[0]
    st = str(first.get("schedule_type") or first.get("shift_type") or "").strip().upper()
    if st in ("ΑΝ", "AN") or "ΡΕΠΟ" in st or "ΑΝΑΠΑΥΣΗ" in st:
        return [{"type": "ΑΝ"}]
    if st in ("ΜΕ", "ME") or "ΜΗ ΕΡΓΑΣΙΑ" in st or "ΜΗΕΡΓΑΣΙΑ" in st.replace(" ", ""):
        return [{"type": "ΜΕ"}]
    entries: list[dict[str, Any]] = []
    for item in rows:
        hf = str(item.get("hour_from") or "").strip()
        ht = str(item.get("hour_to") or "").strip()
        if hf and ht:
            entries.append({"type": "ΕΡΓ", "from": hf, "to": ht})
    # Ώρες κενές χωρίς ρητό ΡΕΠΟ → Μη εργασία.
    return entries or [{"type": "ΜΕ"}]


def _effective_snapshot_for_week_day(row: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(row.get("import_action") or "").strip()
    if action in ("work", "rest", "absent") and not (row.get("validation_errors") or []):
        proposed = row.get("proposed_snapshot")
        if isinstance(proposed, list) and proposed:
            return proposed
    current = row.get("current_snapshot")
    if isinstance(current, list) and current:
        return current
    return []


def _submit_wto_week_with_auth_retry(
    ctx: dict[str, Any],
    client: ErganiClient,
    payload: dict[str, Any],
    bearer: str,
):
    resp = client.document_submit(SUBMISSION_CODE_WTO_WEEK, payload, bearer)
    parsed = json_or_text(resp)
    auth_retry = False
    if resp.status_code in (401, 403):
        from flask import session

        session.pop("ergani_bearer", None)
        refreshed = ensure_ergani_bearer(ctx)
        if refreshed and refreshed != bearer:
            auth_retry = True
            resp = client.document_submit(SUBMISSION_CODE_WTO_WEEK, payload, refreshed)
            parsed = json_or_text(resp)
    return resp, parsed, auth_retry


def apply_import_employee_week(
    ctx: dict[str, Any],
    *,
    employee_rows: list[dict[str, Any]],
    apply_rows: list[dict[str, Any]],
    bearer: str,
    batch_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Μία υποβολή WTOWeek ανά εργαζόμενο για ολόκληρη την εβδομάδα.
    Οι ημέρες χωρίς συμπλήρωση στο Excel συμπληρώνονται από το τρέχον ωράριο.
    """
    if not employee_rows:
        return {"success": False, "error": "Κενή εβδομάδα εργαζομένου", "http_status": 400}

    sample = apply_rows[0] if apply_rows else employee_rows[0]
    emp_afm = str(sample.get("employee_afm") or "").strip()
    last = str(sample.get("eponymo") or "").strip()
    first = str(sample.get("onoma") or "").strip()

    by_date = {
        str(row.get("work_date") or "").strip(): row
        for row in employee_rows
        if str(row.get("work_date") or "").strip()
    }
    work_dates = sorted(by_date.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y"))
    if len(work_dates) != 7:
        return {
            "success": False,
            "error": f"Απαιτούνται 7 ημέρες για WTOWeek (βρέθηκαν {len(work_dates)})",
            "http_status": 400,
        }

    days_payload: list[dict[str, Any]] = []
    seen_days: set[int] = set()
    for work_date in work_dates:
        row = by_date[work_date]
        try:
            day_code = _ergani_weekday(work_date)
        except ValueError as ex:
            return {"success": False, "error": f"Μη έγκυρη ημερομηνία {work_date}", "http_status": 400}
        if day_code in seen_days:
            return {"success": False, "error": f"Διπλή ημέρα εβδομάδας για {work_date}", "http_status": 400}
        seen_days.add(day_code)
        snapshot = _effective_snapshot_for_week_day(row)
        days_payload.append({"day": day_code, "entries": _snapshot_to_week_entries(snapshot)})

    from_iso = ergani_date_to_iso(work_dates[0])
    to_iso = ergani_date_to_iso(work_dates[-1])
    try:
        payload = build_wto_week_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            from_date=str(from_iso or ""),
            to_date=str(to_iso or "") or None,
            comments="Εισαγωγή εβδομαδιαίου ωραρίου από Excel",
            days=days_payload,
        )
    except WorkCardPayloadError as ex:
        return {"success": False, "error": str(ex), "http_status": 400}

    client = ErganiClient(ctx.get("api_base_url"))
    resp, parsed, auth_retry = _submit_wto_week_with_auth_retry(ctx, client, payload, bearer)
    protocol = submit_date = ergani_id = None
    if resp.ok and isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        first_item = parsed[0]
        protocol = first_item.get("protocol")
        submit_date = first_item.get("submitDate")
        raw_id = first_item.get("id")
        ergani_id = str(raw_id).strip() if raw_id is not None else None

    persist_safe(
        _persist_wto_week_submit,
        str(ctx["employer_afm"]),
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
    )

    local_updated_days = 0
    if resp.ok:
        with cursor() as cur:
            upsert_employee(cur, emp_afm, last, first)
        meta = batch_meta if isinstance(batch_meta, dict) else {}
        for row in apply_rows:
            body = _import_row_to_body(row)
            try:
                day_payload = build_wto_daily_payload(
                    branch_aa=str(ctx.get("branch_aa") or "0"),
                    employee_afm=emp_afm,
                    employee_last_name=last,
                    employee_first_name=first,
                    reference_date=str(body.get("reference_date") or ""),
                    schedule_type=str(body.get("schedule_type") or "ΕΡΓ"),
                    hour_from=body.get("hour_from"),
                    hour_to=body.get("hour_to"),
                    intervals=body.get("intervals") if isinstance(body.get("intervals"), list) else None,
                    comments=body.get("comments"),
                )
            except WorkCardPayloadError:
                continue
            work_date_ergani = day_payload["WTOS"]["WTO"][0]["f_from_date"]
            old_schedule = _current_schedule_snapshot(
                ctx, employee_afm=emp_afm, work_date_ergani=work_date_ergani
            )
            updated = _persist_local_schedule_after_wto_daily(
                ctx,
                employee_afm=emp_afm,
                body=body,
                payload=day_payload,
            )
            if updated:
                local_updated_days += 1
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
                local_schedule_updated=updated,
                http_status=resp.status_code,
                success=True,
                source=str(meta.get("source") or "excel_import_wtoweek"),
                import_batch_id=meta.get("batch_id"),
                import_row_id=row.get("id"),
                original_filename=meta.get("original_filename"),
                week_label=meta.get("week_label"),
                error_message=None,
            )

    err_msg = None
    if not resp.ok:
        if isinstance(parsed, dict):
            err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None
        if not err_msg:
            err_msg = response_body_text(resp)[:500] or "Αποτυχία WTOWeek"

    return {
        "success": resp.ok,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "http_status": resp.status_code,
        "local_schedule_updated_days": local_updated_days,
        "auth_retry": auth_retry,
        "error": err_msg,
        "data": parsed,
        "employee_afm": emp_afm,
        "apply_row_ids": [int(r["id"]) for r in apply_rows if r.get("id") is not None],
    }


def _import_batch_date_range_iso(batch_id: int) -> tuple[str | None, str | None]:
    rows = list_import_rows(batch_id)
    isos: list[str] = []
    for row in rows:
        iso = ergani_date_to_iso(str(row.get("work_date") or ""))
        if iso:
            isos.append(iso)
    if not isos:
        return None, None
    isos.sort()
    return isos[0], isos[-1]


def _sync_schedule_after_import(ctx: dict[str, Any], batch_id: int) -> dict[str, Any] | None:
    from_iso, to_iso = _import_batch_date_range_iso(batch_id)
    if not from_iso or not to_iso:
        return None
    try:
        result = fetch_and_save_schedule_for_ctx(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=31,
        )
        return {
            "attempted": True,
            "success": bool(result.get("success")),
            "from": from_iso,
            "to": to_iso,
            "count": int(result.get("count") or 0),
            "detail": str(result.get("detail") or "").strip() or None,
        }
    except Exception as ex:
        current_app.logger.exception("schedule import post-sync failed")
        return {
            "attempted": True,
            "success": False,
            "from": from_iso,
            "to": to_iso,
            "count": 0,
            "detail": str(ex),
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

    apply_rows = list_apply_rows(batch_id)
    if not apply_rows:
        update_batch_status(batch_id, "applied", summary={"applied": 0, "failed": 0, "total": 0})
        return {"success": True, "applied": 0, "failed": 0, "results": []}

    all_rows = list_import_rows(batch_id)
    by_employee_all: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        afm = str(row.get("employee_afm") or "").strip()
        if afm:
            by_employee_all[afm].append(row)
    by_employee_apply: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in apply_rows:
        afm = str(row.get("employee_afm") or "").strip()
        if afm:
            by_employee_apply[afm].append(row)

    update_batch_status(batch_id, "applying")
    applied = 0
    failed = 0
    results: list[dict[str, Any]] = []
    batch_meta = {
        "batch_id": batch_id,
        "original_filename": batch.get("original_filename"),
        "week_label": batch.get("week_label"),
        "source": "excel_import_wtoweek",
    }

    for afm, emp_apply_rows in by_employee_apply.items():
        try:
            result = apply_import_employee_week(
                ctx,
                employee_rows=by_employee_all.get(afm) or [],
                apply_rows=emp_apply_rows,
                bearer=bearer,
                batch_meta=batch_meta,
            )
        except Exception as ex:
            current_app.logger.exception("schedule import WTOWeek apply failed")
            result = {"success": False, "error": str(ex), "http_status": 500, "apply_row_ids": [int(r["id"]) for r in emp_apply_rows if r.get("id") is not None]}

        ok = bool(result.get("success"))
        protocol = str(result.get("protocol") or "") or None
        message = "Εφαρμόστηκε στο Ergani (WTOWeek)" if ok else str(result.get("error") or "Αποτυχία")[:500]
        for row in emp_apply_rows:
            row_id = int(row["id"])
            if ok:
                applied += 1
                update_import_row_result(
                    row_id,
                    apply_status="success",
                    apply_message=message,
                    ergani_protocol=protocol,
                )
            else:
                failed += 1
                update_import_row_result(
                    row_id,
                    apply_status="failed",
                    apply_message=message,
                )
            results.append(
                {
                    "row_id": row_id,
                    "employee_afm": row.get("employee_afm"),
                    "work_date": row.get("work_date"),
                    "success": ok,
                    "protocol": protocol,
                    "error": None if ok else result.get("error"),
                }
            )

    summary = summarize_import_rows(list_import_rows(batch_id))
    summary["applied_ok"] = applied
    summary["applied_failed"] = failed
    summary["employees_submitted"] = len(by_employee_apply)
    summary["submission"] = "WTOWeek"
    final_status = "applied" if failed == 0 else "failed"
    schedule_sync = None
    if applied > 0 or failed > 0:
        schedule_sync = _sync_schedule_after_import(ctx, batch_id)
        if schedule_sync:
            summary["schedule_sync"] = schedule_sync
    update_batch_status(batch_id, final_status, summary=summary)
    record_audit_event(
        action="schedule_import.batch_applied",
        success=failed == 0,
        store_id=int(ctx["id"]),
        employer_afm=str(ctx.get("employer_afm") or ""),
        branch_aa=str(ctx.get("branch_aa") or "0"),
        entity_type="schedule_import_batch",
        entity_id=str(batch_id),
        details={
            "batch_id": batch_id,
            "original_filename": batch.get("original_filename"),
            "week_label": batch.get("week_label"),
            "applied": applied,
            "failed": failed,
            "employees_submitted": len(by_employee_apply),
            "submission": "WTOWeek",
            "final_status": final_status,
            "summary": summary,
            "schedule_sync": schedule_sync,
        },
    )
    return {
        "success": failed == 0,
        "applied": applied,
        "failed": failed,
        "employees_submitted": len(by_employee_apply),
        "submission": "WTOWeek",
        "results": results,
        "summary": summary,
        "schedule_sync": schedule_sync,
    }
