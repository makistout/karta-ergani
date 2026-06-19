"""REST ψηφιακής κάρτας (WRKCardSE) — MSSQL ergani-karta + Ergani API."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request

from app.date_util import format_f_date_time, iso_to_ergani_dates
from app.ergani_client import ErganiClient
from app.http_helpers import (
    bearer_from_request,
    ensure_ergani_bearer,
    json_or_text,
    persist_safe,
    resolve_active_store,
    response_body_text,
)
from app.repo_card import (
    card_event_exists,
    list_card_events_for_store_range,
    persist_wrk_card_submit,
)
from app.repo_entities import find_employee_for_employer
from app.repo_store import get_store_by_afm
from app.work_card_payload import (
    SUBMISSION_CODE_WRK_CARD,
    WorkCardPayloadError,
    build_wrk_card_se_payload,
    f_type_from_event,
    tz_athens,
)
from config import Config

work_card_bp = Blueprint("work_card", __name__, url_prefix="/api/work-card")


def _integration_key_ok() -> bool:
    expected = (Config.WORK_CARD_API_KEY or "").strip()
    if not expected:
        return bool(Config.FLASK_DEBUG)
    got = (request.headers.get("X-Work-Card-Api-Key") or "").strip()
    if not got:
        body = request.get_json(silent=True) or {}
        if isinstance(body, dict):
            got = str(body.get("api_key") or "").strip()
    return bool(got) and secrets.compare_digest(got, expected)


def _resolve_bearer(erg: str, aa: str) -> tuple[str | None, Any, int]:
    bearer = bearer_from_request()
    if bearer:
        return bearer, None, 200
    cfg = get_store_by_afm(erg, aa)
    if not cfg:
        return None, jsonify({
            "error": f"Χωρίς Bearer και χωρίς karta_store_config για ΑΦΜ {erg}"
        }), 401
    try:
        from app.ergani_env import api_login_credentials, client_for_store

        client = client_for_store(cfg)
        api_user, api_pwd, api_ut = api_login_credentials(cfg)
        resp = client.authenticate(api_user, api_pwd, api_ut)
        payload = json_or_text(resp)
        if resp.ok and isinstance(payload, dict):
            token = str(payload.get("accessToken") or "").strip()
            if token:
                return token, None, 200
        return None, jsonify({
            "error": "Αποτυχία αυθεντικοποίησης",
            "upstream_status": resp.status_code,
            "upstream_data": payload,
        }), 401
    except Exception as ex:
        return None, jsonify({"error": str(ex)}), 500


def _resolve_list_dates() -> tuple[str | None, str | None]:
    from_iso = request.args.get("from") or request.args.get("date")
    to_iso = request.args.get("to") or from_iso
    if not from_iso:
        return None, None
    return from_iso.strip()[:10], (to_iso or from_iso).strip()[:10]


def _f_type_label(f_type: str | None) -> str:
    t = str(f_type or "").strip()
    if t == "0":
        return "Είσοδος"
    if t == "1":
        return "Έξοδος"
    return t or "—"


def _submit_work_card(
    *,
    body: dict[str, Any],
    erg_s: str,
    aa_s: str,
    bearer: str,
    api_base_url: str | None = None,
    client_ip: str | None = None,
    client_device: str | None = None,
) -> tuple[Any, int]:
    emp_afm = (body.get("employee_afm") or "").strip()
    last = (body.get("employee_last_name") or body.get("eponymo") or "").strip()
    first = (body.get("employee_first_name") or body.get("onoma") or "").strip()
    event = body.get("event")
    f_type = body.get("f_type")

    if not emp_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400

    from app.db import cursor

    with cursor(commit=False) as cur:
        db_last, db_first, active = find_employee_for_employer(cur, emp_afm, erg_s)
    if active is False:
        return jsonify({"error": "Μη ενεργή σχέση εργασίας στη τοπική βάση"}), 400
    if db_last is None and db_first is None:
        return jsonify({
            "error": "Ο εργαζόμενος δεν βρέθηκε στη βάση — συγχρονίστε εργαζομένους"
        }), 400
    if not last:
        last = (db_last or "").strip()
    if not first:
        first = (db_first or "").strip()

    try:
        resolved_type = f_type_from_event(
            str(event).strip() if event is not None else None,
            str(f_type).strip() if f_type is not None else None,
        )
    except WorkCardPayloadError as e:
        return jsonify({"error": str(e)}), 400

    ref_date = (body.get("reference_date") or "").strip()[:10]
    if not ref_date:
        ref_date = datetime.now(tz_athens()).date().isoformat()

    if card_event_exists(emp_afm, ref_date, resolved_type):
        label = "Είσοδος" if resolved_type == "0" else "Έξοδος"
        return jsonify({
            "error": f"Υπάρχει ήδη {label} για {emp_afm} στις {ref_date}"
        }), 400

    try:
        payload = build_wrk_card_se_payload(
            employer_afm=erg_s,
            branch_aa=aa_s,
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            event=str(event).strip() if event is not None else None,
            f_type=str(f_type).strip() if f_type is not None else None,
            comments=str(body.get("comments") or "").strip() or None,
            reference_date=ref_date,
            event_at=str(body.get("event_at") or "").strip() or None,
            aitiologia=str(body.get("aitiologia") or "").strip() or None,
        )
    except WorkCardPayloadError as e:
        return jsonify({"error": str(e)}), 400

    client = ErganiClient(api_base_url)
    resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
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
        persist_wrk_card_submit,
        SUBMISSION_CODE_WRK_CARD,
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
        client_ip=client_ip,
        client_device=client_device,
    )

    err_msg = None
    if not resp.ok and isinstance(parsed, dict):
        err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None

    return jsonify({
        "success": resp.ok,
        "status": resp.status_code,
        "submission_code": SUBMISSION_CODE_WRK_CARD,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "f_type": resolved_type,
        "f_type_label": _f_type_label(resolved_type),
        "error": err_msg,
        "data": parsed,
    }), resp.status_code if not resp.ok else 200


@work_card_bp.get("/info")
def work_card_info():
    key_set = bool((Config.WORK_CARD_API_KEY or "").strip())
    return jsonify({
        "service": "karta-ergani",
        "database": Config.DB_DATABASE,
        "db_access": "pyodbc only (no SQLAlchemy)",
        "submission_code": SUBMISSION_CODE_WRK_CARD,
        "post_event": "POST /api/work-card/event",
        "post_submit": "POST /api/work-card/submit",
        "list": "GET /api/work-card/list",
        "integration_auth": (
            "X-Work-Card-Api-Key required"
            if key_set
            else "Optional WORK_CARD_API_KEY in .env"
        ),
        "defaults_from_env": {
            "employer_afm": Config.WORK_CARD_DEFAULT_EMPLOYER_AFM or None,
            "branch_aa": Config.WORK_CARD_DEFAULT_BRANCH_AA,
        },
    })


@work_card_bp.get("/list")
def work_card_list():
    """Λίστα επιτυχών δηλώσεων κάρτας για το ενεργό κατάστημα."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "events": []}), 400
    from_iso, to_iso = _resolve_list_dates()
    if not from_iso:
        return jsonify({"error": "Λείπει παράμετρος date ή from/to"}), 400
    try:
        lim = int(request.args.get("limit", "2000"))
    except ValueError:
        lim = 2000
    rows = list_card_events_for_store_range(
        str(ctx["employer_afm"]),
        str(ctx.get("branch_aa") or "0"),
        from_iso,
        to_iso,
        limit=lim,
    )
    for r in rows:
        r["f_type_label"] = _f_type_label(r.get("f_type"))
        r["f_time"] = format_f_date_time(r.get("f_date"))
    iso_dates = iso_to_ergani_dates(from_iso, to_iso, 31)
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "from": from_iso,
        "to": to_iso,
        "work_dates": iso_dates,
        "count": len(rows),
        "events": rows,
    })


@work_card_bp.post("/submit")
def work_card_submit_office():
    """Υποβολή κάρτας από UI γραφείου (ενεργό κατάστημα + session bearer)."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400

    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({"error": "Αποτυχία σύνδεσης Ergani API (web user)"}), 401

    from app.client_request import capture_client_context

    client_ctx = capture_client_context("office_ui")
    return _submit_work_card(
        body=body,
        erg_s=str(ctx["employer_afm"]).strip(),
        aa_s=str(ctx.get("branch_aa") or "0").strip(),
        bearer=bearer,
        api_base_url=ctx.get("api_base_url"),
        client_ip=client_ctx.get("client_ip"),
        client_device=client_ctx.get("client_device"),
    )


@work_card_bp.post("/event")
def work_card_post_event():
    if not _integration_key_ok():
        return jsonify({"error": "Άκυρο X-Work-Card-Api-Key"}), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400

    erg = body.get("employer_afm") or Config.WORK_CARD_DEFAULT_EMPLOYER_AFM
    aa = body.get("branch_aa") or Config.WORK_CARD_DEFAULT_BRANCH_AA
    if not (erg or "").strip():
        return jsonify({"error": "Λείπει employer_afm"}), 400

    erg_s = str(erg).strip()
    aa_s = str(aa or "0").strip()

    bearer, err_resp, err_code = _resolve_bearer(erg_s, aa_s)
    if err_resp is not None:
        return err_resp, err_code

    cfg = get_store_by_afm(erg_s, aa_s)
    api_base = None
    if cfg:
        from app.ergani_env import store_api_context

        api_base = store_api_context(cfg).get("api_base_url")

    from app.client_request import capture_client_context

    client_ctx = capture_client_context("api_event")
    return _submit_work_card(
        body=body,
        erg_s=erg_s,
        aa_s=aa_s,
        bearer=bearer,
        api_base_url=api_base,
        client_ip=client_ctx.get("client_ip"),
        client_device=client_ctx.get("client_device"),
    )
