"""Ειδοποίηση τύπου 2 — τρέχουσα ημέρα: αποστολή, PIN, ενέργειες."""

from __future__ import annotations

from typing import Any

from flask import session

from app import repo_store as repo
from app.notify_pin import verify_notify_pin_for_recipient
from app.repo_notify_recipients import (
    list_deliverable_recipients,
    list_email_deliverable_recipients,
    normalize_mobile,
)
from app.repo_today_alert import (
    create_snooze,
    create_today_alert_token,
    get_today_alert_token_row,
    get_today_alert_token_row_by_id,
    increment_today_alert_pin_attempts,
    mark_today_alert_action,
    mark_today_alert_pin_verified,
    today_alert_token_is_valid,
)
from app.repo_work_log import enrich_work_log_rows_with_schedule
from app.telegram_punch_service import (
    TELEGRAM_PUNCH_SESSION_KEY,
    _activate_store_session,
    _context_from_token_row,
    build_retro_hit_redirect_url,
    resolve_missing_punch_action,
)
from app.today_notify_logic import (
    KIND_LABELS,
    card_action_for_today_kind,
    ergani_date_to_iso,
    today_leave_eligible,
    today_wto_daily_eligible,
)
from app.public_urls import ui_public_url, ui_relative_path

TODAY_ALERT_SESSION_KEY = "today_alert_ctx"


def _context_from_today_row(row: dict[str, Any]) -> dict[str, Any]:
    name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
    kind = str(row.get("notify_kind") or "").strip()
    return {
        "token_id": int(row["id"]),
        "store_id": int(row["store_id"]),
        "store_name": row.get("store_name"),
        "employee_afm": row.get("employee_afm"),
        "employee_name": name or row.get("employee_afm"),
        "eponymo": row.get("eponymo"),
        "onoma": row.get("onoma"),
        "work_date_ergani": row.get("work_date_ergani"),
        "reference_date_iso": row.get("reference_date_iso")
        or ergani_date_to_iso(str(row.get("work_date_ergani") or "")),
        "notify_kind": kind,
        "notify_kind_label": KIND_LABELS.get(kind, kind),
        "hour_from": row.get("hour_from"),
        "hour_to": row.get("hour_to"),
        "schedule_hour_from": row.get("schedule_hour_from"),
        "leave_eligible": today_leave_eligible(
            kind,
            schedule_hour_from=row.get("schedule_hour_from"),
            hour_from=row.get("hour_from"),
            hour_to=row.get("hour_to"),
        ),
        "wto_daily_eligible": today_wto_daily_eligible(kind),
        "wto_hour_from": (row.get("hour_from") or "").strip() or None,
        "wto_hour_to": (row.get("hour_to") or "").strip() or None,
        "wto_schedule_type": "ΕΡΓ",
    }


def _store_today_alert_session(row: dict[str, Any]) -> None:
    session[TODAY_ALERT_SESSION_KEY] = _context_from_today_row(row)


def clear_today_alert_session() -> None:
    session.pop(TODAY_ALERT_SESSION_KEY, None)


def get_today_action_context(*, token: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    ctx = session.get(TODAY_ALERT_SESSION_KEY)
    if isinstance(ctx, dict) and ctx.get("token_id"):
        return ctx, None
    t = (token or "").strip()
    if t:
        row = get_today_alert_token_row(t)
        ok, err = today_alert_token_is_valid(row)
        if not ok or not row:
            return None, err or "Μη έγκυρο token"
        if not row.get("pin_verified_at"):
            return None, (
                "Ανοίξτε τον σύνδεσμο από το Telegram και εισάγετε πρώτα τον PIN σας."
            )
        return _context_from_today_row(row), None
    return None, "Η συνεδρία έληξε — ανοίξτε ξανά τον σύνδεσμο από το Telegram."


def build_today_action_redirect_url(token: str | None = None) -> str:
    """Σχετική διαδρομή — μετά PIN μένει στο ίδιο host."""
    return ui_relative_path("/ui/today-action", token=token)


def build_today_hit_redirect_url(token: str | None = None) -> str:
    """Απόλυτος σύνδεσμος για Telegram/Email."""
    return ui_public_url("/ui/today-hit", token=token)


def today_hit_preview(token: str) -> tuple[dict[str, Any] | None, str | None]:
    row = get_today_alert_token_row(token)
    ok, err = today_alert_token_is_valid(row)
    if not ok:
        return None, err
    assert row is not None
    kind = str(row.get("notify_kind") or "").strip()
    name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
    return {
        "store_name": row.get("store_name"),
        "employee_name": name or row.get("employee_afm"),
        "employee_afm": row.get("employee_afm"),
        "work_date": row.get("work_date_ergani"),
        "notify_kind": kind,
        "notify_kind_label": KIND_LABELS.get(kind, kind),
        "recipient_name": row.get("recipient_name"),
        "notification_kind": "today_alert",
        "wto_daily_eligible": today_wto_daily_eligible(kind),
        "wto_hour_from": (row.get("hour_from") or "").strip() or None,
        "wto_hour_to": (row.get("hour_to") or "").strip() or None,
    }, None


def confirm_today_hit_with_pin(token: str, pin: str) -> tuple[dict[str, Any], int]:
    row = get_today_alert_token_row(token)
    ok, err = today_alert_token_is_valid(row)
    if not ok or not row:
        return {"success": False, "error": err or "Μη έγκυρο token"}, 400

    if not verify_notify_pin_for_recipient(
        store_id=int(row["store_id"]),
        mobile=row.get("mobile"),
        pin=str(pin or "").strip(),
        pin_hash=row.get("notify_pin_hash"),
        pin_plain=row.get("notify_pin"),
    ):
        attempts = increment_today_alert_pin_attempts(int(row["id"]))
        if attempts >= 5:
            return {"success": False, "error": "Λάθος PIN — ο σύνδεσμος κλειδώθηκε"}, 403
        return {"success": False, "error": "Λάθος PIN"}, 401

    try:
        from app.repo_notify_recipients import repair_notify_pin_hash

        repair_notify_pin_hash(
            recipient_id=int(row["recipient_id"]),
            store_id=int(row["store_id"]),
            mobile=row.get("mobile"),
            pin=str(pin or "").strip(),
        )
    except Exception:
        pass

    cfg = repo.get_store_config(int(row["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404

    _activate_store_session(cfg)
    mark_today_alert_pin_verified(int(row["id"]))
    _store_today_alert_session(row)
    return {
        "success": True,
        "redirect": build_today_action_redirect_url(token),
        "detail": "Επιλέξτε ενέργεια για τον εργαζόμενο.",
    }, 200


def snooze_today_alert(*, token: str | None = None) -> tuple[dict[str, Any], int]:
    from app.client_request import capture_client_context
    from app.office_auth import SESSION_USER
    from flask import session

    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    row = get_today_alert_token_row_by_id(int(ctx["token_id"]))
    if not row:
        return {"success": False, "error": "Μη έγκυρο token"}, 400

    office_user = str(session.get(SESSION_USER) or "").strip() or None
    recipient_name = str(row.get("recipient_name") or "").strip() or None
    recipient_mobile = str(row.get("mobile") or "").strip() or None
    client_ctx = capture_client_context(
        "today_snooze",
        extra={
            "recipient_id": row.get("recipient_id"),
            "recipient_name": recipient_name,
            "token_id": row.get("id"),
            "office_user": office_user,
            "employee_afm": row.get("employee_afm"),
            "notify_kind": row.get("notify_kind"),
        },
    )
    acted_by = recipient_name or office_user or "—"
    acted_via = "telegram" if row.get("recipient_id") else "office"

    create_snooze(
        store_id=int(row["store_id"]),
        recipient_id=int(row["recipient_id"]),
        employee_afm=str(row.get("employee_afm") or ""),
        work_date_ergani=str(row.get("work_date_ergani") or ""),
        notify_kind=str(row.get("notify_kind") or ""),
        acted_by_name=acted_by,
        acted_by_mobile=recipient_mobile,
        acted_via=acted_via,
        office_user=office_user,
        client_ip=client_ctx.get("client_ip"),
        client_device=client_ctx.get("client_device"),
    )
    mark_today_alert_action(int(row["id"]), "snooze")
    clear_today_alert_session()
    return {
        "success": True,
        "detail": "Δεν θα σταλεί ξανά ειδοποίηση για αυτή την περίπτωση σήμερα.",
    }, 200


def prepare_card_from_today_alert(*, token: str | None = None) -> tuple[dict[str, Any], int]:
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    row = get_today_alert_token_row_by_id(int(ctx["token_id"]))
    if not row:
        return {"success": False, "error": "Μη έγκυρο token"}, 400

    kind = str(row.get("notify_kind") or "").strip()
    employer_afm = str(row.get("employer_afm") or "")
    branch_aa = str(row.get("branch_aa") or "")
    work_date = str(row.get("work_date_ergani") or "")
    employee_afm = str(row.get("employee_afm") or "")

    action = resolve_missing_punch_action(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        work_date=work_date,
        hour_from=row.get("hour_from"),
        hour_to=row.get("hour_to"),
    )
    if not action:
        sched_row = {
            "employee_afm": employee_afm,
            "work_date": work_date,
            "hour_from": row.get("hour_from"),
            "hour_to": row.get("hour_to"),
        }
        enrich_work_log_rows_with_schedule(
            [sched_row], employer_afm, branch_aa, [work_date]
        )
        sched = sched_row.get("schedule")
        sched_from = str(row.get("schedule_hour_from") or "").strip()
        sched_to = ""
        if isinstance(sched, dict):
            sched_from = sched_from or str(sched.get("hour_from") or "").strip()
            sched_to = str(sched.get("hour_to") or "").strip()
        action = card_action_for_today_kind(
            kind,
            schedule_hour_from=sched_from,
            schedule_hour_to=sched_to,
            hour_from=str(row.get("hour_from") or ""),
        )
    retro_row = {
        **row,
        "card_event": action["card_event"],
        "retro_time": action.get("retro_time") or "",
        "reference_date_iso": row.get("reference_date_iso"),
        "work_date_ergani": row.get("work_date_ergani"),
    }
    session[TELEGRAM_PUNCH_SESSION_KEY] = _context_from_token_row(retro_row)
    mark_today_alert_action(int(row["id"]), "card")
    clear_today_alert_session()
    return {
        "success": True,
        "redirect": build_retro_hit_redirect_url(),
        "detail": "Μετάβαση στην καταχώρηση χτυπήματος κάρτας.",
    }, 200


def mark_today_alert_leave_done(*, token_id: int) -> None:
    mark_today_alert_action(int(token_id), "leave")
    clear_today_alert_session()


def submit_today_leave(
    *,
    leave_type: str,
    comments: str | None = None,
    token: str | None = None,
) -> tuple[dict[str, Any], int]:
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    if not ctx.get("leave_eligible"):
        return {
            "success": False,
            "error": "Η καταχώριση άδειας δεν είναι διαθέσιμη για αυτή την περίπτωση.",
        }, 400

    from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, response_body_text
    from app.ergani_client import ErganiClient
    from app.leave_payload import SUBMISSION_CODE_WTO_LEAVE, build_wto_leave_payload
    from app.repo_card import insert_declaration, parse_ergani_submit_response
    from app.repo_entities import upsert_employee
    from app.work_card_payload import WorkCardPayloadError
    from app.db import cursor
    from app.routes_leave import _persist_leave_submit

    cfg = repo.get_store_config(int(ctx["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404
    _activate_store_session(cfg)
    bearer = ensure_ergani_bearer(cfg)
    if not bearer:
        return {"success": False, "error": "Αποτυχία σύνδεσης Ergani API"}, 401

    emp_afm = str(ctx.get("employee_afm") or "").strip()
    ref_date = str(ctx.get("reference_date_iso") or "").strip()[:10]
    last = str(ctx.get("eponymo") or "").strip()
    first = str(ctx.get("onoma") or "").strip()
    if not emp_afm or not ref_date or not leave_type.strip():
        return {"success": False, "error": "Λείπουν στοιχεία άδειας"}, 400
    if not last or not first:
        return {"success": False, "error": "Λείπουν επώνυμο/όνομα εργαζομένου"}, 400

    try:
        payload = build_wto_leave_payload(
            branch_aa=str(cfg.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            reference_date=ref_date,
            leave_type=leave_type.strip(),
            comments=comments,
        )
    except WorkCardPayloadError as ex:
        return {"success": False, "error": str(ex)}, 400

    client = ErganiClient(cfg.get("api_base_url"))
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
        str(cfg["employer_afm"]),
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
        mark_today_alert_leave_done(token_id=int(ctx["token_id"]))

    err_msg = None
    if not resp.ok and isinstance(parsed, dict):
        err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None

    return {
        "success": resp.ok,
        "protocol": protocol,
        "submit_date": submit_date,
        "error": err_msg,
    }, (200 if resp.ok else 502)




def mark_today_alert_wto_done(*, token_id: int) -> None:
    mark_today_alert_action(int(token_id), "wto_daily")
    clear_today_alert_session()


def submit_today_wto_daily(
    *,
    hour_from: str | None = None,
    hour_to: str | None = None,
    comments: str | None = None,
    token: str | None = None,
) -> tuple[dict[str, Any], int]:
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    if not ctx.get("wto_daily_eligible"):
        return {
            "success": False,
            "error": "Η αλλαγή ωραρίου δεν είναι διαθέσιμη για αυτή την περίπτωση.",
        }, 400

    from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, response_body_text
    from app.ergani_client import ErganiClient
    from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY, build_wto_daily_payload
    from app.work_card_payload import WorkCardPayloadError
    from app.routes_wto_daily import _persist_wto_daily_submit

    cfg = repo.get_store_config(int(ctx["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404
    _activate_store_session(cfg)
    bearer = ensure_ergani_bearer(cfg)
    if not bearer:
        return {"success": False, "error": "Αποτυχία σύνδεσης Ergani API"}, 401

    emp_afm = str(ctx.get("employee_afm") or "").strip()
    ref_date = str(ctx.get("reference_date_iso") or "").strip()[:10]
    last = str(ctx.get("eponymo") or "").strip()
    first = str(ctx.get("onoma") or "").strip()
    hf = str(hour_from or ctx.get("wto_hour_from") or "").strip()
    ht = str(hour_to if hour_to is not None else ctx.get("wto_hour_to") or "").strip()
    if not emp_afm or not ref_date or not hf:
        return {"success": False, "error": "Λείπουν στοιχεία ωραρίου"}, 400
    if not last or not first:
        return {"success": False, "error": "Λείπουν επώνυμο/όνομα εργαζομένου"}, 400

    try:
        payload = build_wto_daily_payload(
            branch_aa=str(cfg.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            reference_date=ref_date,
            schedule_type=str(ctx.get("wto_schedule_type") or "ΕΡΓ"),
            hour_from=hf,
            hour_to=ht or None,
            comments=comments,
        )
    except WorkCardPayloadError as ex:
        return {"success": False, "error": str(ex)}, 400

    client = ErganiClient(cfg.get("api_base_url"))
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
        str(cfg["employer_afm"]),
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
    )
    if resp.ok:
        from app.db import cursor
        from app.repo_entities import upsert_employee

        with cursor() as cur:
            upsert_employee(cur, emp_afm, last, first)
        mark_today_alert_wto_done(token_id=int(ctx["token_id"]))

    err_msg = None
    if not resp.ok and isinstance(parsed, dict):
        err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None

    return {
        "success": resp.ok,
        "protocol": protocol,
        "submit_date": submit_date,
        "error": err_msg,
    }, (200 if resp.ok else 502)



from app.today_alert_notifications import send_today_punch_notifications, send_wto_schedule_notifications
