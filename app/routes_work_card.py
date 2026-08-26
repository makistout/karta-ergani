"""REST ψηφιακής κάρτας (WRKCardSE) — MSSQL ergani-karta + Ergani API."""

from __future__ import annotations

import json
import hashlib
import secrets
from datetime import datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, request, session

from app.audit_log import record_audit_event
from app.date_util import format_date_for_ergani, format_f_date_time, iso_to_ergani_dates
from app.ergani_client import ErganiClient
from app.http_helpers import (
    bearer_from_request,
    ensure_ergani_bearer,
    json_or_text,
    normalize_multiline_text,
    resolve_active_store,
    response_body_text,
)
from app.repo_card import (
    card_event_exists,
    list_card_events_for_store_date,
    list_card_events_for_store_range,
    persist_wrk_card_submit,
)
from app.repo_entities import find_employee_for_employer
from app.repo_card_listener import (
    attach_job_declaration,
    cancel_queued_job_for_fallback,
    enqueue_job,
    get_listener_settings,
    wait_for_job,
)
from app.repo_store import get_store_by_afm
from app.work_card_payload import (
    SUBMISSION_CODE_WRK_CARD,
    WorkCardPayloadError,
    aitiologia_for_wrk_card_submit,
    build_wrk_card_se_payload,
    f_type_from_event,
    RETRO_AITIOLOGIA_INTERNET,
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


def _wrk_card_error_message(resp, parsed: Any) -> str | None:
    """Αναλυτικό μήνυμα σφάλματος Ergani για καταγραφές/UI."""
    if resp.ok:
        return None
    parts: list[str] = []

    def _add(msg: Any) -> None:
        text = str(msg or "").strip()
        if text and text not in parts:
            parts.append(text)

    if isinstance(parsed, dict):
        for key in ("message", "Message", "error", "Error", "detail", "Detail", "title"):
            _add(parsed.get(key))
        errors = parsed.get("errors") or parsed.get("Errors")
        if isinstance(errors, list):
            for item in errors:
                if isinstance(item, dict):
                    _add(item.get("message") or item.get("Message") or item.get("error"))
                else:
                    _add(item)
        elif isinstance(errors, str):
            _add(errors)
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                _add(item.get("message") or item.get("Message") or item.get("error"))
            else:
                _add(str(item))
    elif isinstance(parsed, str):
        _add(parsed)

    if not parts:
        body = response_body_text(resp)
        if body:
            _add(body[:600])

    if parts:
        return normalize_multiline_text(f"Ergani ({resp.status_code}): " + " · ".join(parts))

    from app.ergani_errors import ergani_failure_detail

    return ergani_failure_detail(resp, SUBMISSION_CODE_WRK_CARD)


def _ergani_requires_aitiologia(parsed: Any) -> bool:
    try:
        text = json.dumps(parsed, ensure_ascii=False)
    except TypeError:
        text = str(parsed or "")
    low = text.lower()
    return "f_aitiologia" in low and (
        "expected" in low or "possible elements" in low or "incomplete content" in low
    )


def _ergani_missing_aitiologia(parsed: Any) -> bool:
    """Ergani ζητά λόγο καθυστέρησης (όχι όταν απαγορεύεται)."""
    try:
        text = json.dumps(parsed, ensure_ascii=False)
    except TypeError:
        text = str(parsed or "")
    low = text.lower()
    if "δεν πρέπει να δηλώνεται λόγος καθυστέρησης" in low:
        return False
    if "συμπληρώσετε" in low and "λόγο καθυστέρησης" in low:
        return True
    if "εκτός του επιτρεπόμενου χρονικού ορίου" in low:
        return True
    if "εκπρόθεσμ" in low:
        return True
    return _ergani_requires_aitiologia(parsed)


def _ergani_forbids_aitiologia(parsed: Any) -> bool:
    from app.work_card_payload import ergani_forbids_aitiologia

    return ergani_forbids_aitiologia(parsed)


def _ergani_duplicate_registration(parsed: Any) -> bool:
    try:
        text = json.dumps(parsed, ensure_ascii=False)
    except TypeError:
        text = str(parsed or "")
    low = text.lower()
    return "υπάρχει ήδη είσοδος" in low or "υπάρχει ήδη έξοδος" in low


def _latest_existing_card_event(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    reference_date: str,
    f_type: str,
) -> dict[str, Any] | None:
    rows = list_card_events_for_store_date(
        employer_afm,
        branch_aa,
        reference_date,
        limit=100,
    )
    for row in rows:
        if (
            str(row.get("f_afm") or "").strip() == str(employee_afm or "").strip()
            and str(row.get("f_type") or "").strip() == str(f_type or "").strip()
        ):
            return row
    return None


def _correction_offer_payload(
    *,
    employee_afm: str,
    employee_name: str,
    reference_date: str,
    f_type: str,
    attempted_event_at: str | None,
    existing_event: dict[str, Any] | None,
) -> dict[str, Any]:
    label = _f_type_label(f_type)
    existing_time = format_f_date_time((existing_event or {}).get("f_date"))
    attempted_time = format_f_date_time(attempted_event_at)
    msg = (
        f"Υπάρχει ήδη {label} για {employee_name or employee_afm} στις "
        f"{format_date_for_ergani(reference_date)}"
    )
    if existing_time:
        msg += f" ώρα {existing_time}"
    if attempted_time:
        msg += f". Νέο χτύπημα: {attempted_time}."
    else:
        msg += "."
    msg += " Θέλετε να προχωρήσουμε σε διόρθωση;"
    return {
        "success": False,
        "correction_available": True,
        "error": msg,
        "f_type": f_type,
        "f_type_label": label,
        "reference_date": reference_date,
        "employee_afm": employee_afm,
        "employee_name": employee_name or None,
        "existing_event": {
            "time": existing_time,
            "protocol": (existing_event or {}).get("protocol"),
            "ergani_id": (existing_event or {}).get("ergani_submission_id"),
        },
        "attempted_event": {
            "time": attempted_time,
        },
    }


def _submit_work_card(
    *,
    body: dict[str, Any],
    erg_s: str,
    aa_s: str,
    bearer: str,
    api_base_url: str | None = None,
    client_ip: str | None = None,
    client_device: str | None = None,
    store_id: int | None = None,
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
    explicit_event_at = bool(str(body.get("event_at") or "").strip())
    event_at_str = str(body.get("event_at") or "").strip() or None
    correction_mode = bool(body.get("correction_mode"))
    employee_display = str(body.get("employee_name") or "").strip() or f"{first} {last}".strip()

    if resolved_type == "1":
        from app.work_card_guards import (
            checkout_requires_entry_error,
            has_entry_for_checkout,
            normalize_overnight_checkout_reference,
        )

        # Ζωντανή έξοδος χωρίς event_at: τώρα (πριν το overnight normalize).
        if not event_at_str:
            event_at_str = datetime.now(tz_athens()).isoformat(timespec="seconds")

        ref_date, event_at_str = normalize_overnight_checkout_reference(
            employer_afm=erg_s,
            branch_aa=aa_s,
            employee_afm=emp_afm,
            reference_date_iso=ref_date,
            event_at=event_at_str,
        )

        if not has_entry_for_checkout(
            employer_afm=erg_s,
            branch_aa=aa_s,
            employee_afm=emp_afm,
            reference_date_iso=ref_date,
            event_at=event_at_str,
        ):
            return jsonify(checkout_requires_entry_error()), 400

    if card_event_exists(emp_afm, ref_date, resolved_type) and not correction_mode:
        existing_event = _latest_existing_card_event(
            employer_afm=erg_s,
            branch_aa=aa_s,
            employee_afm=emp_afm,
            reference_date=ref_date,
            f_type=resolved_type,
        )
        return jsonify(
            _correction_offer_payload(
                employee_afm=emp_afm,
                employee_name=employee_display,
                reference_date=ref_date,
                f_type=resolved_type,
                attempted_event_at=event_at_str,
                existing_event=existing_event,
            )
        ), 409

    requested_aitiologia = str(body.get("aitiologia") or "").strip() or None
    submitted_at = datetime.now(tz_athens())
    if not event_at_str:
        event_at_str = submitted_at.isoformat(timespec="seconds")
    try:
        batch_index = int(body.get("batch_index") or 0)
        batch_total = int(body.get("batch_total") or 0)
    except (TypeError, ValueError):
        batch_index = 0
        batch_total = 0
    if batch_total > 1 and batch_index >= 1 and explicit_event_at:
        from app.punch_batch_stagger import apply_batch_stagger_to_event_at

        event_at_str = apply_batch_stagger_to_event_at(
            event_at_str,
            reference_date=ref_date,
            punch_index=batch_index - 1,
            punch_total=batch_total,
        )
    aitiologia_raw = aitiologia_for_wrk_card_submit(
        f_type=resolved_type,
        reference_date=ref_date,
        event_at=event_at_str,
        employer_afm=erg_s,
        branch_aa=aa_s,
        employee_afm=emp_afm,
        requested_aitiologia=requested_aitiologia,
        submitted_at=submitted_at,
    )
    explicit_aitiologia = requested_aitiologia is not None and aitiologia_raw is not None

    def build_payload(
        resolved_aitiologia: str | None,
        *,
        include_null_aitiologia: bool = False,
    ):
        return build_wrk_card_se_payload(
            employer_afm=erg_s,
            branch_aa=aa_s,
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            event=str(event).strip() if event is not None else None,
            f_type=str(f_type).strip() if f_type is not None else None,
            comments=str(body.get("comments") or "").strip() or None,
            reference_date=ref_date,
            event_at=event_at_str,
            aitiologia=resolved_aitiologia,
            include_null_aitiologia=include_null_aitiologia,
        )

    try:
        payload = build_payload(aitiologia_raw)
    except WorkCardPayloadError as e:
        return jsonify({"error": str(e)}), 400

    # Listener routing is deliberately limited to WRKCardSE. Stores that have not
    # explicitly selected it continue through the original direct path below.
    listener_routing_selected = False
    listener_fallback_reason: str | None = None
    if store_id is not None:
        try:
            listener_cfg = get_listener_settings(int(store_id))
        except Exception:
            current_app.logger.exception("Unable to read card-listener routing; using erganiOS path")
            listener_cfg = {"card_submission_mode": "erganios"}
        active_device = listener_cfg.get("device") or {}
        listener_online = bool(active_device.get("is_online"))
        listener_routing_selected = listener_cfg.get("card_submission_mode") == "listener"
        if listener_routing_selected and not listener_online:
            listener_fallback_reason = "listener_offline"
        if listener_cfg.get("card_submission_mode") == "listener" and listener_online:
            canonical = json.dumps(
                {"store_id": int(store_id), "payload": payload},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            idempotency_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            timeout_seconds = int(listener_cfg.get("listener_offline_seconds") or 60)
            try:
                queued = enqueue_job(
                    store_id=int(store_id),
                    idempotency_key=idempotency_key,
                    employee_afm=emp_afm,
                    f_type=resolved_type,
                    reference_date=ref_date,
                    event_at=event_at_str,
                    payload=payload,
                    ergani_api_base_url=str(api_base_url or Config.ERGANI_API_BASE_URL),
                    fallback_seconds=timeout_seconds,
                )
                listener_job = wait_for_job(queued["job_uuid"], int(store_id), timeout_seconds)
            except Exception:
                current_app.logger.exception("Card-listener dispatch failed before submission; using erganiOS path")
                listener_job = None
                queued = None

            listener_aitiologia_retry = False
            if (
                queued
                and listener_job
                and str(listener_job.get("status")) == "failed"
                and not aitiologia_raw
                and _ergani_missing_aitiologia(
                    listener_job.get("result_data")
                    or {"error": listener_job.get("error_summary")}
                )
            ):
                # The direct erganiOS route already retries this Ergani 400.
                # Do the same through the selected listener: create a second,
                # distinct job with the required delay reason and never fall
                # back directly after the listener has handled the first job.
                retry_payload = build_payload(RETRO_AITIOLOGIA_INTERNET)
                retry_canonical = json.dumps(
                    {"store_id": int(store_id), "payload": retry_payload},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                retry_idempotency_key = hashlib.sha256(
                    retry_canonical.encode("utf-8")
                ).hexdigest()
                try:
                    retry_queued = enqueue_job(
                        store_id=int(store_id),
                        idempotency_key=retry_idempotency_key,
                        employee_afm=emp_afm,
                        f_type=resolved_type,
                        reference_date=ref_date,
                        event_at=event_at_str,
                        payload=retry_payload,
                        ergani_api_base_url=str(api_base_url or Config.ERGANI_API_BASE_URL),
                        fallback_seconds=timeout_seconds,
                    )
                    retry_job = wait_for_job(
                        retry_queued["job_uuid"], int(store_id), timeout_seconds
                    )
                    queued = retry_queued
                    listener_job = retry_job
                    payload = retry_payload
                    aitiologia_raw = RETRO_AITIOLOGIA_INTERNET
                    listener_aitiologia_retry = True
                except Exception:
                    current_app.logger.exception(
                        "Card-listener aitiologia retry dispatch failed"
                    )

            if (
                queued
                and listener_job
                and str(listener_job.get("status")) == "failed"
                and aitiologia_raw
                and not explicit_aitiologia
                and _ergani_forbids_aitiologia(
                    listener_job.get("result_data")
                    or {"error": listener_job.get("error_summary")}
                )
            ):
                # Clock/minute-boundary safety: if Ergani still considers the
                # event within 15', repeat through the same listener without a reason.
                retry_payload = build_payload(None, include_null_aitiologia=True)
                retry_canonical = json.dumps(
                    {"store_id": int(store_id), "payload": retry_payload},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                retry_idempotency_key = hashlib.sha256(
                    retry_canonical.encode("utf-8")
                ).hexdigest()
                try:
                    retry_queued = enqueue_job(
                        store_id=int(store_id),
                        idempotency_key=retry_idempotency_key,
                        employee_afm=emp_afm,
                        f_type=resolved_type,
                        reference_date=ref_date,
                        event_at=event_at_str,
                        payload=retry_payload,
                        ergani_api_base_url=str(api_base_url or Config.ERGANI_API_BASE_URL),
                        fallback_seconds=timeout_seconds,
                    )
                    retry_job = wait_for_job(
                        retry_queued["job_uuid"], int(store_id), timeout_seconds
                    )
                    queued = retry_queued
                    listener_job = retry_job
                    payload = retry_payload
                    aitiologia_raw = None
                    listener_aitiologia_retry = True
                except Exception:
                    current_app.logger.exception(
                        "Card-listener removal-of-aitiologia retry dispatch failed"
                    )

            if listener_job and listener_job.get("status") in {"succeeded", "failed", "needs_review"}:
                job_status = str(listener_job.get("status"))
                listener_ok = job_status == "succeeded"
                listener_http_status = int(listener_job.get("upstream_http_status") or (200 if listener_ok else 502))
                listener_data = listener_job.get("result_data")
                listener_protocol = listener_job.get("protocol")
                listener_submit_date = listener_job.get("submit_date_text")
                listener_ergani_id = listener_job.get("ergani_submission_id")
                persist_error = None
                persisted = False
                try:
                    declaration_id = persist_wrk_card_submit(
                        SUBMISSION_CODE_WRK_CARD,
                        listener_http_status,
                        listener_ok,
                        payload,
                        json.dumps(listener_data, ensure_ascii=False) if listener_data is not None else None,
                        listener_protocol,
                        listener_submit_date,
                        listener_ergani_id,
                        replace_existing=correction_mode,
                        client_ip=client_ip,
                        client_device=client_device,
                        submission_channel="listener",
                        submission_ip=listener_job.get("submission_ip"),
                        executor_instance=listener_job.get("executor_instance"),
                    )
                    attach_job_declaration(queued["job_uuid"], int(store_id), declaration_id)
                    persisted = bool(listener_ok)
                except Exception as ex:
                    persist_error = str(ex)
                    current_app.logger.exception("Unable to persist listener WRKCardSE result")

                record_audit_event(
                    action="work_card_punch_submit",
                    success=bool(listener_ok and persisted),
                    http_status=listener_http_status,
                    store_id=store_id,
                    employer_afm=erg_s,
                    branch_aa=aa_s,
                    entity_type="employee",
                    entity_id=emp_afm,
                    details={
                        "source": str(body.get("source") or "office_ui")[:32],
                        "employee_afm": emp_afm,
                        "employee_name": employee_display or None,
                        "event": str(event or "").strip() or None,
                        "f_type": resolved_type,
                        "f_type_label": _f_type_label(resolved_type),
                        "reference_date": ref_date,
                        "event_at": event_at_str,
                        "protocol": listener_protocol,
                        "ergani_submission_id": listener_ergani_id,
                        "submission_channel": "listener",
                        "submission_ip": listener_job.get("submission_ip"),
                        "executor_instance": listener_job.get("executor_instance"),
                        "listener_job_uuid": queued["job_uuid"],
                        "listener_status": job_status,
                        "aitiologia_retry": listener_aitiologia_retry,
                        "aitiologia": aitiologia_raw,
                        "ergani_http_status": listener_http_status,
                        "ergani_response": listener_data,
                        "error_message": listener_job.get("error_summary"),
                        "persist_error": persist_error,
                    },
                    client_ip=client_ip,
                    client_device=client_device,
                )
                if listener_ok and not persisted:
                    return jsonify({
                        "success": False, "status": 500, "submission_code": SUBMISSION_CODE_WRK_CARD,
                        "protocol": listener_protocol, "submit_date": listener_submit_date,
                        "ergani_submission_id": listener_ergani_id, "persisted": False,
                        "error": "Ergani success through listener, but local persistence failed",
                        "data": listener_data,
                    }), 500
                return jsonify({
                    "success": listener_ok,
                    "status": listener_http_status,
                    "submission_code": SUBMISSION_CODE_WRK_CARD,
                    "protocol": listener_protocol,
                    "submit_date": listener_submit_date,
                    "ergani_submission_id": listener_ergani_id,
                    "f_type": resolved_type,
                    "f_type_label": _f_type_label(resolved_type),
                    "persisted": persisted,
                    "correction_mode": correction_mode,
                    "work_log_sync_triggered": False,
                    "error": listener_job.get("error_summary"),
                    "data": listener_data,
                    "submission_channel": "listener",
                    "aitiologia_retry": listener_aitiologia_retry,
                }), 200 if listener_ok else listener_http_status

            if queued:
                # Direct fallback is safe only if the listener has not leased the job.
                if not cancel_queued_job_for_fallback(queued["job_uuid"], int(store_id)):
                    current = wait_for_job(queued["job_uuid"], int(store_id), 2)
                    return jsonify({
                        "success": False,
                        "status": 202,
                        "error": "Το χτύπημα έχει παραληφθεί από τον listener και αναμένεται η απάντηση του ΕΡΓΑΝΗ.",
                        "listener_job_uuid": queued["job_uuid"],
                        "listener_status": (current or {}).get("status"),
                    }), 202
                listener_fallback_reason = "listener_timeout"

    client = ErganiClient(api_base_url)
    resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
    parsed = json_or_text(resp)
    aitiologia_retry = False
    if not resp.ok and not explicit_aitiologia and _ergani_missing_aitiologia(parsed):
        try:
            payload = build_payload(None, include_null_aitiologia=True)
        except WorkCardPayloadError as e:
            return jsonify({"error": str(e)}), 400
        resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
        parsed = json_or_text(resp)
        aitiologia_retry = True
    if not resp.ok and not explicit_aitiologia and _ergani_missing_aitiologia(parsed):
        aitiologia_raw = RETRO_AITIOLOGIA_INTERNET
        try:
            payload = build_payload(aitiologia_raw)
        except WorkCardPayloadError as e:
            return jsonify({"error": str(e)}), 400
        resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
        parsed = json_or_text(resp)
        aitiologia_retry = True

    # Αν ο Ergani απαγορεύει τη δήλωση λόγου, κάνουμε retry *χωρίς* f_aitiologia.
    if not resp.ok and not explicit_aitiologia and _ergani_forbids_aitiologia(parsed):
        try:
            # Κρατάμε το στοιχείο f_aitiologia (null) ώστε να ικανοποιείται το XSD,
            # αλλά δεν δηλώνουμε λόγο καθυστέρησης.
            payload = build_payload(None, include_null_aitiologia=True)
        except WorkCardPayloadError as e:
            return jsonify({"error": str(e)}), 400
        resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
        parsed = json_or_text(resp)
        aitiologia_retry = True
    if not resp.ok and not correction_mode and _ergani_duplicate_registration(parsed):
        existing_event = _latest_existing_card_event(
            employer_afm=erg_s,
            branch_aa=aa_s,
            employee_afm=emp_afm,
            reference_date=ref_date,
            f_type=resolved_type,
        )
        return jsonify(
            _correction_offer_payload(
                employee_afm=emp_afm,
                employee_name=employee_display,
                reference_date=ref_date,
                f_type=resolved_type,
                attempted_event_at=event_at_str,
                existing_event=existing_event,
            )
        ), 409
    protocol = submit_date = ergani_id = None
    if resp.ok and isinstance(parsed, list) and parsed:
        first_item = parsed[0]
        if isinstance(first_item, dict):
            protocol = first_item.get("protocol")
            submit_date = first_item.get("submitDate")
            raw_id = first_item.get("id")
            ergani_id = str(raw_id).strip() if raw_id is not None else None

    persist_error: str | None = None
    persisted = False
    from app.submission_identity import server_submission_identity
    submission_ip, executor_instance = server_submission_identity()
    try:
        persist_wrk_card_submit(
            SUBMISSION_CODE_WRK_CARD,
            resp.status_code,
            resp.ok,
            payload,
            response_body_text(resp),
            protocol,
            submit_date,
            ergani_id,
            replace_existing=correction_mode,
            client_ip=client_ip,
            client_device=client_device,
            submission_channel="erganios",
            submission_ip=submission_ip,
            executor_instance=executor_instance,
        )
        persisted = bool(resp.ok)
    except Exception as ex:
        persist_error = str(ex)
        if resp.ok:
            current_app.logger.exception(
                "Αποτυχία αποθήκευσης χτυπήματος κάρτας στη βάση erganiOS"
            )

    err_msg = _wrk_card_error_message(resp, parsed)
    submit_source = str(body.get("source") or "office_ui").strip()[:32] or "office_ui"
    record_audit_event(
        action="work_card_punch_submit",
        success=bool(resp.ok and persisted),
        http_status=int(resp.status_code or 0),
        store_id=store_id,
        employer_afm=erg_s,
        branch_aa=aa_s,
        entity_type="employee",
        entity_id=emp_afm,
        details={
            "source": submit_source,
            "employee_afm": emp_afm,
            "employee_name": employee_display or None,
            "event": str(event or "").strip() or None,
            "f_type": resolved_type,
            "f_type_label": _f_type_label(resolved_type),
            "reference_date": ref_date,
            "event_at": event_at_str,
            "protocol": protocol,
            "ergani_submission_id": ergani_id,
            "ergani_ok": resp.ok,
            "persisted": persisted,
            "persist_error": persist_error,
            "batch_index": body.get("batch_index"),
            "batch_total": body.get("batch_total"),
            "auth_retry": bool(body.get("auth_retry")),
            "aitiologia_retry": aitiologia_retry,
            "aitiologia": aitiologia_raw,
            "correction_mode": correction_mode,
            "error": err_msg,
            "error_message": err_msg,
            "ergani_http_status": int(resp.status_code or 0),
            "submission_channel": "erganios",
            "listener_routing_selected": listener_routing_selected,
            "listener_fallback_reason": listener_fallback_reason,
            "submission_ip": submission_ip,
            "executor_instance": executor_instance,
            "ergani_response": parsed if not resp.ok else None,
        },
        client_ip=client_ip,
        client_device=client_device,
    )

    if resp.ok and not persisted:
        return jsonify({
            "success": False,
            "status": 500,
            "submission_code": SUBMISSION_CODE_WRK_CARD,
            "protocol": protocol,
            "submit_date": submit_date,
            "ergani_submission_id": ergani_id,
            "f_type": resolved_type,
            "f_type_label": _f_type_label(resolved_type),
            "persisted": False,
            "error": (
                "Ergani επιτυχία αλλά αποτυχία αποθήκευσης στη βάση erganiOS"
                + (f": {persist_error}" if persist_error else "")
            ),
            "data": parsed,
        }), 500

    return jsonify({
        "success": resp.ok,
        "status": resp.status_code,
        "submission_code": SUBMISSION_CODE_WRK_CARD,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "f_type": resolved_type,
        "f_type_label": _f_type_label(resolved_type),
        "persisted": persisted,
        "correction_mode": correction_mode,
        "work_log_sync_triggered": False,
        "submission_channel": "erganios",
        "listener_routing_selected": listener_routing_selected,
        "listener_fallback_reason": listener_fallback_reason,
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
    response, status = _submit_work_card(
        body=body,
        erg_s=str(ctx["employer_afm"]).strip(),
        aa_s=str(ctx.get("branch_aa") or "0").strip(),
        bearer=bearer,
        api_base_url=ctx.get("api_base_url"),
        client_ip=client_ctx.get("client_ip"),
        client_device=client_ctx.get("client_device"),
        store_id=int(ctx["id"]),
    )
    if status != 401:
        return response, status

    session.pop("ergani_bearer", None)
    session.pop("ergani_bearer_store_id", None)
    session.pop("ergani_bearer_env", None)
    refreshed = ensure_ergani_bearer(ctx)
    if not refreshed:
        return response, status
    retry_body = dict(body)
    retry_body["auth_retry"] = True
    return _submit_work_card(
        body=retry_body,
        erg_s=str(ctx["employer_afm"]).strip(),
        aa_s=str(ctx.get("branch_aa") or "0").strip(),
        bearer=refreshed,
        api_base_url=ctx.get("api_base_url"),
        client_ip=client_ctx.get("client_ip"),
        client_device=client_ctx.get("client_device"),
        store_id=int(ctx["id"]),
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
        store_id=int(cfg["id"]) if cfg and cfg.get("id") else None,
    )
