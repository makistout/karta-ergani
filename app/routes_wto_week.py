"""Υποβολή σταθερού εβδομαδιαίου ωραρίου (WTOWeek) ανά εργαζόμενο."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from flask import Blueprint, jsonify, request, session

from app.date_util import format_date_for_ergani
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
from app.repo_schedule import upsert_schedule_for_employee_day
from app.work_card_payload import WorkCardPayloadError, norm_afm
from app.wto_week_payload import SUBMISSION_CODE_WTO_WEEK, build_wto_week_payload

wto_week_bp = Blueprint("wto_week", __name__, url_prefix="/api/wto-week")
logger = logging.getLogger(__name__)

# Χωρίς ημερομηνία λήξης: υλικοποίηση τοπικών ημερών ώστε Αρχική/ωράριο
# να δείχνουν αμέσως χωρίς αναμονή portal sync.
_OPEN_ENDED_LOCAL_WEEKS = 8


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


def _ergani_weekday(d: date) -> int:
    """Ergani f_day: 0=Κυριακή … 6=Σάββατο."""
    return (d.weekday() + 1) % 7


def _parse_iso_day(value: str | None) -> date | None:
    raw = str(value or "").strip()[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def _day_entries_by_code(days: Any) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    if not isinstance(days, list):
        return out
    for row in days:
        if not isinstance(row, dict):
            continue
        try:
            day = int(row.get("day"))
        except (TypeError, ValueError):
            continue
        entries = row.get("entries")
        if isinstance(entries, list):
            out[day] = [e for e in entries if isinstance(e, dict)]
    return out


def _local_shift_and_intervals(
    entries: list[dict[str, Any]],
) -> tuple[str, list[dict[str, str]] | None]:
    types = {
        str(e.get("type") or "").strip().upper()
        for e in entries
        if str(e.get("type") or "").strip()
    }
    if "ΑΝ" in types or "AN" in types:
        return "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", None
    if "ΜΕ" in types or "ME" in types:
        return "ΜΗ ΕΡΓΑΣΙΑ", None
    intervals: list[dict[str, str]] = []
    primary = "ΕΡΓ"
    for entry in entries:
        entry_type = str(entry.get("type") or "ΕΡΓ").strip().upper() or "ΕΡΓ"
        if entry_type in {"ΤΗΛ", "TEL"}:
            primary = "ΤΗΛ"
        hf = str(entry.get("from") or entry.get("hour_from") or "").strip()
        ht = str(entry.get("to") or entry.get("hour_to") or "").strip()
        if hf or ht:
            intervals.append({"hour_from": hf, "hour_to": ht})
    return primary, intervals or [{"hour_from": None, "hour_to": None}]


def _persist_local_schedule_after_wto_week(
    ctx: dict[str, Any],
    *,
    employee_afm: str,
    from_date: str,
    to_date: str | None,
    days: Any,
) -> int:
    """Υλικοποίηση τοπικού karta_schedule από το πρότυπο εβδομάδας (χωρίς αναμονή sync)."""
    start = _parse_iso_day(from_date)
    if not start:
        return 0
    end = _parse_iso_day(to_date)
    if end is None:
        end = start + timedelta(days=7 * _OPEN_ENDED_LOCAL_WEEKS - 1)
    if end < start:
        return 0

    by_day = _day_entries_by_code(days)
    if len(by_day) != 7:
        return 0

    updated = 0
    try:
        cursor_day = start
        while cursor_day <= end:
            entries = by_day.get(_ergani_weekday(cursor_day)) or []
            shift_type, intervals = _local_shift_and_intervals(entries)
            is_rest = shift_type in {"ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "ΜΗ ΕΡΓΑΣΙΑ"}
            upsert_schedule_for_employee_day(
                str(ctx["employer_afm"]),
                str(ctx.get("branch_aa") or "0"),
                format_date_for_ergani(cursor_day.isoformat()),
                employee_afm=employee_afm,
                hour_from=None if is_rest else (intervals or [{}])[0].get("hour_from"),
                hour_to=None if is_rest else (intervals or [{}])[0].get("hour_to"),
                shift_type=shift_type,
                extra="local WTOWeek submit",
                source_aa="local_wto_week",
                intervals=None if is_rest else intervals,
            )
            updated += 1
            cursor_day += timedelta(days=1)
    except Exception:
        logger.exception("Failed to persist local WTOWeek schedule")
        return 0
    return updated


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
    local_days_updated = 0
    if resp.ok:
        with cursor() as cur:
            upsert_employee(
                cur,
                employee_afm,
                str(employee.get("eponymo") or ""),
                str(employee.get("onoma") or ""),
            )
        local_days_updated = _persist_local_schedule_after_wto_week(
            ctx,
            employee_afm=employee_afm,
            from_date=str(body.get("from_date") or ""),
            to_date=str(body.get("to_date") or "").strip() or None,
            days=body.get("days"),
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
        "local_schedule_days_updated": local_days_updated,
        "error": error,
        "data": parsed,
    }), (200 if resp.ok else 502)
