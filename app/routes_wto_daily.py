"""Υποβολή ημερήσιου ωραρίου (WTODaily) — Οργάνωση Χρόνου Εργασίας."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, current_app, jsonify, request, session

from app.ergani_client import ErganiClient
from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, resolve_active_store, response_body_text
from app.repo_card import insert_declaration, parse_ergani_submit_response
from app.repo_entities import upsert_employee
from app.audit_log import record_audit_event
from app.repo_schedule import list_schedule_for_store, upsert_schedule_for_employee_day
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY, build_wto_daily_payload
from app.work_card_payload import WorkCardPayloadError, norm_afm
from app.db import cursor

wto_daily_bp = Blueprint("wto_daily", __name__, url_prefix="/api/wto-daily")


def _persist_wto_daily_submit(
    employer_afm: str,
    http_status: int,
    success: bool,
    request_dict: dict[str, Any],
    response_body: str | None,
    protocol: str | None,
    submit_date_text: str | None,
    ergani_submission_id: str | None = None,
) -> None:
    req_str = json.dumps(request_dict, ensure_ascii=False)
    parsed_id, parsed_proto, parsed_date = parse_ergani_submit_response(response_body)
    with cursor() as cur:
        insert_declaration(
            cur,
            SUBMISSION_CODE_WTO_DAILY,
            norm_afm(employer_afm),
            protocol or parsed_proto,
            submit_date_text or parsed_date,
            ergani_submission_id or parsed_id,
            http_status,
            success,
            req_str,
            response_body,
        )


def _normalize_schedule_type_for_local(value: Any) -> str:
    schedule_type = str(value or "ΕΡΓ").strip().upper()
    if schedule_type == "AN":
        return "ΑΝ"
    return schedule_type or "ΕΡΓ"


def _clear_ergani_bearer_session() -> None:
    session.pop("ergani_bearer", None)
    session.pop("ergani_bearer_store_id", None)
    session.pop("ergani_bearer_env", None)


def _ergani_authorization_denied(resp: Any, parsed: Any = None) -> bool:
    try:
        if int(getattr(resp, "status_code", 0) or 0) in (401, 403):
            return True
    except Exception:
        pass

    parts: list[str] = []
    if isinstance(parsed, dict):
        for key in ("message", "Message", "error", "Error", "detail", "Detail"):
            value = parsed.get(key)
            if value:
                parts.append(str(value))
    elif isinstance(parsed, str):
        parts.append(parsed)
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                for key in ("message", "Message", "error", "Error", "detail", "Detail"):
                    value = item.get(key)
                    if value:
                        parts.append(str(value))
            elif item:
                parts.append(str(item))

    body = response_body_text(resp)
    if body:
        parts.append(body)
    text = " ".join(parts).lower()
    return "authorization has been denied" in text


def _submit_wto_daily_with_auth_retry(
    ctx: dict[str, Any],
    client: ErganiClient,
    payload: dict[str, Any],
    bearer: str,
) -> tuple[Any, Any, bool]:
    resp = client.document_submit(SUBMISSION_CODE_WTO_DAILY, payload, bearer)
    parsed = json_or_text(resp)
    if not _ergani_authorization_denied(resp, parsed):
        return resp, parsed, False

    _clear_ergani_bearer_session()
    refreshed = ensure_ergani_bearer(ctx)
    if not refreshed:
        return resp, parsed, False

    resp = client.document_submit(SUBMISSION_CODE_WTO_DAILY, payload, refreshed)
    parsed = json_or_text(resp)
    return resp, parsed, True


def _local_schedule_intervals(body: dict[str, Any], *, is_rest: bool) -> list[dict[str, str]] | None:
    if is_rest:
        return None
    raw = body.get("intervals")
    out: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            hf = str(item.get("hour_from") or "").strip()
            ht = str(item.get("hour_to") or "").strip()
            if hf or ht:
                out.append({"hour_from": hf, "hour_to": ht})
    if out:
        return out
    return [
        {
            "hour_from": str(body.get("hour_from") or "").strip(),
            "hour_to": str(body.get("hour_to") or "").strip(),
        }
    ]


def _schedule_snapshot(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "hour_from": str(row.get("hour_from") or "").strip() or None,
                "hour_to": str(row.get("hour_to") or "").strip() or None,
                "shift_type": str(row.get("shift_type") or "").strip() or None,
                "source_aa": str(row.get("source_aa") or "").strip() or None,
            }
        )
    return out


def _current_schedule_snapshot(
    ctx: dict[str, Any],
    *,
    employee_afm: str,
    work_date_ergani: str,
) -> list[dict[str, Any]]:
    try:
        rows = list_schedule_for_store(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            work_date_ergani,
        )
        emp = norm_afm(employee_afm)
        return _schedule_snapshot(
            [row for row in rows if norm_afm(row.get("employee_afm") or "") == emp]
        )
    except Exception:
        try:
            current_app.logger.exception("Failed to read current schedule for WTODaily audit")
        except Exception:
            pass
        return []


def _requested_schedule_snapshot(body: dict[str, Any]) -> list[dict[str, Any]]:
    schedule_type = _normalize_schedule_type_for_local(body.get("schedule_type"))
    is_rest = schedule_type == "ΑΝ"
    if is_rest:
        return [
            {
                "hour_from": None,
                "hour_to": None,
                "shift_type": "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ",
                "source_aa": "local_wto_daily",
            }
        ]
    return [
        {
            "hour_from": item.get("hour_from") or None,
            "hour_to": item.get("hour_to") or None,
            "shift_type": schedule_type,
            "source_aa": "local_wto_daily",
        }
        for item in (_local_schedule_intervals(body, is_rest=False) or [])
    ]


def record_wto_daily_schedule_audit(
    ctx: dict[str, Any],
    *,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date_ergani: str,
    body: dict[str, Any],
    old_schedule: list[dict[str, Any]],
    protocol: str | None,
    ergani_submission_id: str | None,
    local_schedule_updated: bool,
    http_status: int,
    success: bool,
) -> None:
    new_schedule = (
        _current_schedule_snapshot(
            ctx,
            employee_afm=employee_afm,
            work_date_ergani=work_date_ergani,
        )
        if local_schedule_updated
        else _requested_schedule_snapshot(body)
    )
    record_audit_event(
        action="wto_daily.schedule_change",
        success=success,
        http_status=http_status,
        store_id=int(ctx["id"]) if ctx.get("id") is not None else None,
        employer_afm=str(ctx.get("employer_afm") or ""),
        branch_aa=str(ctx.get("branch_aa") or "0"),
        entity_type="employee",
        entity_id=norm_afm(employee_afm),
        details={
            "employee_afm": norm_afm(employee_afm),
            "employee_name": f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip() or None,
            "work_date": work_date_ergani,
            "old_schedule": old_schedule,
            "new_schedule": new_schedule,
            "requested_schedule": _requested_schedule_snapshot(body),
            "schedule_type": _normalize_schedule_type_for_local(body.get("schedule_type")),
            "protocol": protocol,
            "ergani_submission_id": ergani_submission_id,
            "local_schedule_updated": bool(local_schedule_updated),
        },
    )


def _persist_local_schedule_after_wto_daily(
    ctx: dict[str, Any],
    *,
    employee_afm: str,
    body: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    schedule_type = _normalize_schedule_type_for_local(body.get("schedule_type"))
    is_rest = schedule_type == "ΑΝ"
    intervals = _local_schedule_intervals(body, is_rest=is_rest)
    try:
        upsert_schedule_for_employee_day(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            payload["WTOS"]["WTO"][0]["f_from_date"],
            employee_afm=employee_afm,
            hour_from=None if is_rest else body.get("hour_from"),
            hour_to=None if is_rest else body.get("hour_to"),
            shift_type="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ" if is_rest else schedule_type,
            extra="local WTODaily submit",
            source_aa="local_wto_daily",
            intervals=intervals,
        )
        return True
    except Exception:
        current_app.logger.exception("Failed to persist local WTODaily schedule")
        return False


@wto_daily_bp.post("/submit")
def submit_wto_daily():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400

    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({"error": "Αποτυχία σύνδεσης Ergani API (web user)"}), 401

    emp_afm = str(body.get("employee_afm") or "").strip()
    ref_date = str(body.get("reference_date") or "").strip()[:10]
    if not emp_afm or not ref_date:
        return jsonify({"error": "Απαιτούνται employee_afm, reference_date"}), 400

    last = str(body.get("eponymo") or "").strip()
    first = str(body.get("onoma") or "").strip()
    if not last or not first:
        return jsonify({"error": "Απαιτούνται επώνυμο και όνομα εργαζομένου"}), 400

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
        return jsonify({"error": str(ex)}), 400
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
    if not resp.ok and isinstance(parsed, dict):
        err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None

    return jsonify({
        "success": resp.ok,
        "submission_code": SUBMISSION_CODE_WTO_DAILY,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "http_status": resp.status_code,
        "local_schedule_updated": local_schedule_updated,
        "auth_retry": auth_retry,
        "error": err_msg,
        "data": parsed,
    }), (200 if resp.ok else 502)
