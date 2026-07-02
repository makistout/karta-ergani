"""Υποβολή ημερήσιου ωραρίου (WTODaily) — Οργάνωση Χρόνου Εργασίας."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from app.ergani_client import ErganiClient
from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, resolve_active_store, response_body_text
from app.repo_card import insert_declaration, parse_ergani_submit_response
from app.repo_entities import upsert_employee
from app.repo_schedule import upsert_schedule_for_employee_day
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


def _persist_local_schedule_after_wto_daily(
    ctx: dict[str, Any],
    *,
    employee_afm: str,
    body: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    schedule_type = _normalize_schedule_type_for_local(body.get("schedule_type"))
    is_rest = schedule_type == "ΑΝ"
    try:
        upsert_schedule_for_employee_day(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            payload["WTOS"]["WTO"][0]["f_from_date"],
            employee_afm=employee_afm,
            hour_from=None if is_rest else body.get("hour_from"),
            hour_to=None if is_rest else body.get("hour_to"),
            shift_type="Ρεπό/ανάπαυση" if is_rest else schedule_type,
            extra="local WTODaily submit",
            source_aa="local_wto_daily",
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
            comments=body.get("comments"),
        )
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400

    client = ErganiClient(ctx.get("api_base_url"))
    resp = client.document_submit(SUBMISSION_CODE_WTO_DAILY, payload, bearer)
    parsed = json_or_text(resp)
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
        "error": err_msg,
        "data": parsed,
    }), (200 if resp.ok else 502)
