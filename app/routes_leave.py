"""Υποβολή άδειας (WTOLeave) — Οργάνωση Χρόνου Εργασίας."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request

from app.ergani_client import ErganiClient
from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, resolve_active_store, response_body_text
from app.leave_payload import SUBMISSION_CODE_WTO_LEAVE, build_wto_leave_payload
from app.leave_types import LEAVE_TYPES
from app.repo_card import insert_declaration, parse_ergani_submit_response
from app.repo_entities import upsert_employee
from app.work_card_payload import WorkCardPayloadError, norm_afm
from app.db import cursor

leave_bp = Blueprint("leave", __name__, url_prefix="/api/leave")


def _persist_leave_submit(
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
            SUBMISSION_CODE_WTO_LEAVE,
            norm_afm(employer_afm),
            protocol or parsed_proto,
            submit_date_text or parsed_date,
            ergani_submission_id or parsed_id,
            http_status,
            success,
            req_str,
            response_body,
        )


@leave_bp.get("/types")
def list_leave_types():
    return jsonify({"types": LEAVE_TYPES})


@leave_bp.post("/submit")
def submit_leave():
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
    leave_type = str(body.get("leave_type") or "").strip()
    if not emp_afm or not ref_date or not leave_type:
        return jsonify({"error": "Απαιτούνται employee_afm, reference_date, leave_type"}), 400

    last = str(body.get("eponymo") or "").strip()
    first = str(body.get("onoma") or "").strip()
    if not last or not first:
        return jsonify({"error": "Απαιτούνται επώνυμο και όνομα εργαζομένου"}), 400

    try:
        payload = build_wto_leave_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            reference_date=ref_date,
            leave_type=leave_type,
            comments=body.get("comments"),
            hour_from=body.get("hour_from"),
            hour_to=body.get("hour_to"),
        )
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400

    client = ErganiClient(ctx.get("api_base_url"))
    resp = client.document_submit(SUBMISSION_CODE_WTO_LEAVE, payload, bearer)
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
        _persist_leave_submit,
        str(ctx["employer_afm"]),
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
    )

    if resp.ok:
        with cursor() as cur:
            upsert_employee(cur, emp_afm, last, first)

    err_msg = None
    if not resp.ok and isinstance(parsed, dict):
        err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None

    return jsonify({
        "success": resp.ok,
        "submission_code": SUBMISSION_CODE_WTO_LEAVE,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "http_status": resp.status_code,
        "error": err_msg,
        "data": parsed,
    }), (200 if resp.ok else 502)
