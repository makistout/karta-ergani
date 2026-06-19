"""Ειδοποίηση τύπου 2 — τρέχουσα ημέρα: αποστολή, PIN, ενέργειες."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from flask import session

from app import repo_store as repo
from app.notify_pin import verify_notify_pin
from app.repo_notify_recipients import list_deliverable_recipients, normalize_mobile
from app.repo_today_alert import (
    create_snooze,
    create_today_alert_token,
    get_today_alert_token_row,
    get_today_alert_token_row_by_id,
    increment_today_alert_pin_attempts,
    is_snoozed,
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
)
from app.today_notify_logic import (
    KIND_LABELS,
    card_action_for_today_kind,
    ergani_date_to_iso,
    resolve_today_notify_kind,
    today_leave_eligible,
)
from config import Config

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
    base = (Config.PUBLIC_BASE_URL or "").rstrip("/") or ""
    path = f"{base}/ui/today-action" if base else "/ui/today-action"
    t = (token or "").strip()
    if t:
        return f"{path}?t={quote(t, safe='')}"
    return path


def build_today_hit_redirect_url(token: str | None = None) -> str:
    base = (Config.PUBLIC_BASE_URL or "").rstrip("/") or ""
    path = f"{base}/ui/today-hit" if base else "/ui/today-hit"
    t = (token or "").strip()
    if t:
        return f"{path}?t={quote(t, safe='')}"
    return path


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
    }, None


def confirm_today_hit_with_pin(token: str, pin: str) -> tuple[dict[str, Any], int]:
    row = get_today_alert_token_row(token)
    ok, err = today_alert_token_is_valid(row)
    if not ok or not row:
        return {"success": False, "error": err or "Μη έγκυρο token"}, 400

    if not verify_notify_pin(
        store_id=int(row["store_id"]),
        mobile=normalize_mobile(row.get("mobile")),
        pin=str(pin or "").strip(),
        pin_hash=row.get("notify_pin_hash"),
    ):
        attempts = increment_today_alert_pin_attempts(int(row["id"]))
        if attempts >= 5:
            return {"success": False, "error": "Λάθος PIN — ο σύνδεσμος κλειδώθηκε"}, 403
        return {"success": False, "error": "Λάθος PIN"}, 401

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
    action = card_action_for_today_kind(
        kind,
        schedule_hour_from=str(row.get("schedule_hour_from") or ""),
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


def send_today_punch_notifications(
    *,
    store_id: int,
    store_name: str,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date: str,
    hour_from: str | None,
    hour_to: str | None,
    notify_kind: str | None,
    public_base_url: str,
) -> dict[str, Any]:
    from app.telegram_notify import (
        TelegramNotConfigured,
        format_today_alert_notification,
        send_telegram_message,
    )

    row: dict[str, Any] = {
        "employee_afm": employee_afm,
        "work_date": work_date,
        "hour_from": hour_from,
        "hour_to": hour_to,
        "eponymo": eponymo,
        "onoma": onoma,
    }
    enrich_work_log_rows_with_schedule(
        [row], employer_afm, branch_aa, [work_date]
    )
    sched = row.get("schedule") if isinstance(row.get("schedule"), dict) else {}
    schedule_hour_from = str((sched or {}).get("hour_from") or "").strip() or None

    resolved_kind = resolve_today_notify_kind(row)
    if not resolved_kind:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "no_alert",
        }
    if notify_kind and notify_kind.strip() != resolved_kind:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "kind_mismatch",
        }
    if is_snoozed(
        store_id=store_id,
        employee_afm=employee_afm,
        work_date_ergani=work_date,
        notify_kind=resolved_kind,
    ):
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "snoozed",
        }

    recipients = list_deliverable_recipients(store_id)
    sent = 0
    errors: list[str] = []
    ref_iso = ergani_date_to_iso(work_date)

    for rec in recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
            continue
        hit_url = None
        if (rec.get("notify_pin_hash") or "").strip():
            try:
                token = create_today_alert_token(
                    recipient_id=int(rec["id"]),
                    store_id=store_id,
                    employee_afm=employee_afm,
                    eponymo=eponymo,
                    onoma=onoma,
                    work_date_ergani=work_date,
                    reference_date_iso=ref_iso,
                    notify_kind=resolved_kind,
                    hour_from=hour_from,
                    hour_to=hour_to,
                    schedule_hour_from=schedule_hour_from,
                )
                hit_url = build_today_hit_redirect_url(token)
            except Exception as ex:
                errors.append(f"{rec.get('name')}: token — {ex}")
        text = format_today_alert_notification(
            store_name=store_name,
            employee_afm=employee_afm,
            eponymo=eponymo,
            onoma=onoma,
            work_date=work_date,
            notify_kind=resolved_kind,
            hit_url=hit_url,
            has_pin=bool((rec.get("notify_pin_hash") or "").strip()),
        )
        try:
            send_telegram_message(chat_id, text)
            sent += 1
        except Exception as ex:
            errors.append(f"{rec.get('name')}: {ex}")

    return {
        "sent": sent,
        "total": len(recipients),
        "errors": errors,
        "notify_kind": resolved_kind,
    }
