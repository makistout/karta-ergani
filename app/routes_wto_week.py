"""Υποβολή σταθερού εβδομαδιαίου ωραρίου (WTOWeek) ανά εργαζόμενο."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request, session

from app.db import cursor
from app.ergani_client import ErganiClient
from app.http_helpers import (
    ensure_ergani_bearer,
    json_or_text,
    persist_safe,
    resolve_active_store,
    response_body_text,
)
from app.repo_card import insert_declaration, parse_ergani_submit_response
from app.repo_entities import list_employees_for_employer, upsert_employee
from app.work_card_payload import WorkCardPayloadError, norm_afm
from app.wto_week_payload import SUBMISSION_CODE_WTO_WEEK, build_wto_week_payload

wto_week_bp = Blueprint("wto_week", __name__, url_prefix="/api/wto-week")


def _submission_codes(payload: Any) -> list[str]:
    if not isinstance(payload, list):
        return []
    return [
        str(item.get("code") or item.get("Code") or "").strip()
        for item in payload
        if isinstance(item, dict)
    ]


def _availability(client: ErganiClient, bearer: str) -> tuple[bool, int, Any]:
    resp = client.submissions_list(bearer)
    parsed = json_or_text(resp)
    return resp.ok and SUBMISSION_CODE_WTO_WEEK in _submission_codes(parsed), resp.status_code, parsed


def _availability_with_token_refresh(
    ctx: dict[str, Any],
    client: ErganiClient,
) -> tuple[str | None, bool, int, Any]:
    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return None, False, 401, None

    available, status, parsed = _availability(client, bearer)
    if status not in (401, 403):
        return bearer, available, status, parsed

    session.pop("ergani_bearer", None)
    refreshed = ensure_ergani_bearer(ctx)
    if not refreshed or refreshed == bearer:
        return bearer, available, status, parsed

    available, status, parsed = _availability(client, refreshed)
    return refreshed, available, status, parsed


def _employee_for_active_store(ctx: dict[str, Any], employee_afm: str) -> dict[str, Any] | None:
    target = norm_afm(employee_afm)
    rows = list_employees_for_employer(
        str(ctx["employer_afm"]),
        branch_aa=str(ctx.get("branch_aa") or "0"),
        active_only=True,
        limit=5000,
    )
    return next((row for row in rows if str(row.get("afm") or "").strip() == target), None)


def _persist_submit(
    employer_afm: str,
    http_status: int,
    success: bool,
    request_dict: dict[str, Any],
    response_body: str | None,
    protocol: str | None,
    submit_date_text: str | None,
    ergani_submission_id: str | None = None,
) -> None:
    parsed_id, parsed_protocol, parsed_date = parse_ergani_submit_response(response_body)
    with cursor() as cur:
        insert_declaration(
            cur,
            SUBMISSION_CODE_WTO_WEEK,
            norm_afm(employer_afm),
            protocol or parsed_protocol,
            submit_date_text or parsed_date,
            ergani_submission_id or parsed_id,
            http_status,
            success,
            json.dumps(request_dict, ensure_ascii=False),
            response_body,
        )


@wto_week_bp.get("/availability")
def wto_week_availability():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"available": False, "error": "Επιλέξτε πρώτα κατάστημα"}), 400
    client = ErganiClient(ctx.get("api_base_url"))
    bearer, available, status, parsed = _availability_with_token_refresh(ctx, client)
    if not bearer:
        return jsonify({"available": False, "error": "Αποτυχία σύνδεσης Ergani API"}), 401
    if status >= 400:
        return jsonify({
            "available": False,
            "error": "Αποτυχία ελέγχου ενεργών υποβολών Ergani",
            "upstream_status": status,
            "data": parsed,
        }), 502
    return jsonify({
        "available": available,
        "submission_code": SUBMISSION_CODE_WTO_WEEK,
        "store": {"id": ctx["id"], "name": ctx["name"]},
    })


@wto_week_bp.post("/submit")
def submit_wto_week():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400

    client = ErganiClient(ctx.get("api_base_url"))
    bearer, available, status, parsed_availability = _availability_with_token_refresh(ctx, client)
    if not bearer:
        return jsonify({"error": "Αποτυχία σύνδεσης Ergani API (web user)"}), 401
    if status >= 400:
        return jsonify({
            "error": "Αποτυχία ελέγχου ενεργών υποβολών Ergani",
            "upstream_status": status,
            "data": parsed_availability,
        }), 502
    if not available:
        return jsonify({
            "error": "Το WTOWeek δεν είναι ενεργό για τον συνδεδεμένο χρήστη Ergani",
        }), 409

    employee_afm = str(body.get("employee_afm") or "").strip()
    if not employee_afm:
        return jsonify({"error": "Απαιτείται employee_afm"}), 400
    try:
        employee = _employee_for_active_store(ctx, employee_afm)
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400
    if not employee:
        return jsonify({"error": "Ο εργαζόμενος δεν είναι ενεργός στο επιλεγμένο παράρτημα"}), 404

    try:
        payload = build_wto_week_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=employee_afm,
            employee_last_name=str(employee.get("eponymo") or ""),
            employee_first_name=str(employee.get("onoma") or ""),
            from_date=str(body.get("from_date") or ""),
            to_date=str(body.get("to_date") or "").strip() or None,
            comments=body.get("comments"),
            days=body.get("days"),
        )
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400

    resp = client.document_submit(SUBMISSION_CODE_WTO_WEEK, payload, bearer)
    parsed = json_or_text(resp)
    ergani_id = protocol = submit_date = None
    if resp.ok and isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        first = parsed[0]
        raw_id = first.get("id")
        ergani_id = str(raw_id).strip() if raw_id is not None else None
        protocol = str(first.get("protocol") or "").strip() or None
        submit_date = str(first.get("submitDate") or "").strip() or None

    persist_safe(
        _persist_submit,
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
            upsert_employee(
                cur,
                employee_afm,
                str(employee.get("eponymo") or ""),
                str(employee.get("onoma") or ""),
            )

    error = None
    if not resp.ok and isinstance(parsed, dict):
        error = str(parsed.get("message") or parsed.get("Message") or "").strip() or None
    return jsonify({
        "success": resp.ok,
        "submission_code": SUBMISSION_CODE_WTO_WEEK,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "http_status": resp.status_code,
        "error": error,
        "data": parsed,
    }), (200 if resp.ok else 502)
