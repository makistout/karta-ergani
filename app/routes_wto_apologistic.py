"""Υποβολή απολογιστικών εγγράφων ΟΧΕ (WTODailyA, WTOOvA)."""

from __future__ import annotations

from typing import Any, Callable

from flask import Blueprint, jsonify, request

from app.audit_log import record_audit_event
from app.http_helpers import ensure_ergani_bearer, resolve_active_store
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY_A, build_wto_daily_a_payload
from app.wto_ov_payload import SUBMISSION_CODE_WTO_OV_A, build_wto_ov_a_payload
from app.wto_submit import (
    ergani_error_message,
    execute_wto_document_submit,
    parse_submit_response,
)
from app.work_card_payload import WorkCardPayloadError, norm_afm

wto_apologistic_bp = Blueprint("wto_apologistic", __name__)


def json_submit_result(
    *,
    submission_code: str,
    resp: Any,
    parsed: Any,
    auth_retry: bool,
    extra: dict[str, Any] | None = None,
) -> tuple[Any, int]:
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    payload = {
        "success": resp.ok,
        "submission_code": submission_code,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "http_status": resp.status_code,
        "auth_retry": auth_retry,
        "error": ergani_error_message(parsed),
        "data": parsed,
    }
    if extra:
        payload.update(extra)
    return jsonify(payload), (200 if resp.ok else 502)


def record_apologistic_submit_audit(
    ctx: dict[str, Any],
    *,
    action: str,
    employee_afm: str,
    reference_date: str,
    submission_code: str,
    success: bool,
    http_status: int,
    protocol: str | None,
    ergani_submission_id: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    audit_details: dict[str, Any] = {
        "submission_code": submission_code,
        "employee_afm": norm_afm(employee_afm),
        "reference_date": reference_date,
        "protocol": protocol,
        "ergani_submission_id": ergani_submission_id,
    }
    if details:
        audit_details.update(details)
    record_audit_event(
        action=action,
        success=success,
        http_status=http_status,
        store_id=int(ctx["id"]) if ctx.get("id") is not None else None,
        employer_afm=str(ctx.get("employer_afm") or ""),
        branch_aa=str(ctx.get("branch_aa") or "0"),
        entity_type="employee",
        entity_id=norm_afm(employee_afm),
        details=audit_details,
    )


def execute_apologistic_wto_submit(
    ctx: dict[str, Any],
    *,
    submission_code: str,
    payload: dict[str, Any],
    audit_action: str,
    employee_afm: str,
    reference_date: str,
    audit_details: dict[str, Any] | None = None,
) -> tuple[Any | None, Any, bool, int | None]:
    resp, parsed, auth_retry, declaration_id = execute_wto_document_submit(
        ctx,
        submission_code=submission_code,
        payload=payload,
        refresh_bearer=ensure_ergani_bearer,
    )
    if resp is None:
        return resp, parsed, auth_retry, declaration_id
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    record_apologistic_submit_audit(
        ctx,
        action=audit_action,
        employee_afm=employee_afm,
        reference_date=reference_date,
        submission_code=submission_code,
        success=resp.ok,
        http_status=resp.status_code,
        protocol=protocol,
        ergani_submission_id=ergani_id,
        details=audit_details,
    )
    return resp, parsed, auth_retry, declaration_id


def _submit_from_body(
    ctx: dict[str, Any],
    body: dict[str, Any],
    *,
    submission_code: str,
    build_payload: Callable[..., dict[str, Any]],
    audit_action: str,
) -> tuple[Any, int]:
    emp_afm = str(body.get("employee_afm") or "").strip()
    ref_date = str(body.get("reference_date") or "").strip()[:10]
    last = str(body.get("eponymo") or "").strip()
    first = str(body.get("onoma") or "").strip()
    if not emp_afm or not ref_date:
        return jsonify({"error": "Απαιτούνται employee_afm, reference_date"}), 400
    if not last or not first:
        return jsonify({"error": "Απαιτούνται επώνυμο και όνομα εργαζομένου"}), 400

    try:
        common = dict(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            reference_date=ref_date,
            comments=body.get("comments"),
        )
        if submission_code == SUBMISSION_CODE_WTO_DAILY_A:
            payload = build_payload(
                **common,
                schedule_type=str(body.get("schedule_type") or "ΕΡΓ"),
                hour_from=body.get("hour_from"),
                hour_to=body.get("hour_to"),
                intervals=body.get("intervals") if isinstance(body.get("intervals"), list) else None,
            )
        else:
            payload = build_payload(
                **common,
                hour_from=body.get("hour_from"),
                hour_to=body.get("hour_to"),
                intervals=body.get("intervals") if isinstance(body.get("intervals"), list) else None,
            )
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400

    resp, parsed, auth_retry, _declaration_id = execute_apologistic_wto_submit(
        ctx,
        submission_code=submission_code,
        payload=payload,
        audit_action=audit_action,
        employee_afm=emp_afm,
        reference_date=ref_date,
        audit_details={"source": str(body.get("source") or "manual")[:32]},
    )
    if resp is None:
        return jsonify(parsed), 401
    return json_submit_result(
        submission_code=submission_code,
        resp=resp,
        parsed=parsed,
        auth_retry=auth_retry,
    )


@wto_apologistic_bp.post("/api/wto-daily-a/submit")
def submit_wto_daily_a():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400
    return _submit_from_body(
        ctx,
        body,
        submission_code=SUBMISSION_CODE_WTO_DAILY_A,
        build_payload=build_wto_daily_a_payload,
        audit_action="wto_daily_a.submit",
    )


@wto_apologistic_bp.post("/api/wto-ov-a/submit")
def submit_wto_ov_a():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400
    return _submit_from_body(
        ctx,
        body,
        submission_code=SUBMISSION_CODE_WTO_OV_A,
        build_payload=build_wto_ov_a_payload,
        audit_action="wto_ov_a.submit",
    )
