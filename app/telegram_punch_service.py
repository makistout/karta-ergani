"""Εκτέλεση χτυπήματος κάρτας από token Telegram + PIN."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from flask import session

from app import repo_store as repo
from app.notify_pin import verify_notify_pin_for_recipient
from app.repo_notify_recipients import normalize_mobile
from app.repo_telegram_punch import (
    get_punch_token_row,
    increment_pin_attempts,
    mark_pin_verified,
    mark_token_used,
    token_is_valid,
)
from app.repo_work_log import enrich_work_log_rows_with_card_punch
from config import Config

TELEGRAM_PUNCH_SESSION_KEY = "telegram_punch_ctx"
RETRO_AITIOLOGIA = "001"


def ergani_date_to_iso(work_date: str) -> str:
    s = (work_date or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            continue
    return s[:10]


def resolve_missing_punch_action(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date: str,
    hour_from: str | None,
    hour_to: str | None,
) -> dict[str, str] | None:
    """Επιστρέφει card_event + retro_time για ελλιπές χτύπημα (παρελθόν)."""
    from app.repo_card import card_event_exists

    hf = (hour_from or "").strip()
    ht = (hour_to or "").strip()
    if hf and ht:
        return None
    ref_iso = ergani_date_to_iso(work_date)
    if not ref_iso:
        return None
    has_in = card_event_exists(employee_afm, ref_iso, "0")
    has_out = card_event_exists(employee_afm, ref_iso, "1")
    if has_in and has_out:
        return None
    if not hf and not has_in:
        event = "check_in"
    elif not ht and not has_out:
        event = "check_out"
    else:
        return None
    row: dict[str, Any] = {
        "employee_afm": employee_afm,
        "work_date": work_date,
        "hour_from": hour_from,
        "hour_to": hour_to,
    }
    enrich_work_log_rows_with_card_punch([row], employer_afm, branch_aa)
    return {
        "card_event": event,
        "retro_time": str(row.get("retro_time") or "").strip(),
    }


def missing_punch_notify_skip_reason(
    *,
    employee_afm: str,
    work_date: str,
    hour_from: str | None,
    hour_to: str | None,
) -> str | None:
    """Λόγος μη αποστολής· None = επιτρέπεται ειδοποίηση (αν υπάρχει action)."""
    from app.repo_card import card_event_exists

    hf = (hour_from or "").strip()
    ht = (hour_to or "").strip()
    if hf and ht:
        return "complete"
    ref_iso = ergani_date_to_iso(work_date)
    if not ref_iso:
        return "invalid_date"
    has_in = card_event_exists(employee_afm, ref_iso, "0")
    has_out = card_event_exists(employee_afm, ref_iso, "1")
    if has_in and has_out:
        return "already_submitted"
    if not hf and has_in:
        return "already_submitted"
    if not ht and has_out:
        return "already_submitted"
    return None


def _context_from_token_row(row: dict[str, Any]) -> dict[str, Any]:
    name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
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
        "retro_time": row.get("retro_time"),
        "card_event": row.get("card_event") or "check_in",
    }


def _store_punch_session(row: dict[str, Any]) -> None:
    session[TELEGRAM_PUNCH_SESSION_KEY] = _context_from_token_row(row)


def get_retro_hit_context(
    *, token: str | None = None
) -> tuple[dict[str, Any] | None, str | None]:
    ctx = session.get(TELEGRAM_PUNCH_SESSION_KEY)
    if isinstance(ctx, dict) and ctx.get("token_id"):
        return ctx, None
    t = (token or "").strip()
    if t:
        row = get_punch_token_row(t)
        ok, err = token_is_valid(row)
        if not ok or not row:
            return None, err or "Μη έγκυρο token"
        if not row.get("pin_verified_at"):
            return None, (
                "Ανοίξτε τον σύνδεσμο από το Telegram και εισάγετε πρώτα τον PIN σας."
            )
        return _context_from_token_row(row), None
    return None, "Η συνεδρία έληξε — ανοίξτε ξανά τον σύνδεσμο από το Telegram."


def clear_retro_hit_session() -> None:
    session.pop(TELEGRAM_PUNCH_SESSION_KEY, None)


def submit_retro_hit_from_session(
    *,
    event: str,
    reference_date: str,
    retro_time: str,
    aitiologia: str = RETRO_AITIOLOGIA,
    token: str | None = None,
) -> tuple[dict[str, Any], int]:
    ctx, err = get_retro_hit_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401

    token_id = int(ctx["token_id"])
    row = None
    from app.repo_telegram_punch import get_punch_token_row_by_id

    row = get_punch_token_row_by_id(token_id)
    if row:
        ok, verr = token_is_valid(row)
        if not ok:
            clear_retro_hit_session()
            return {"success": False, "error": verr or "Μη έγκυρο token"}, 400

    cfg = repo.get_store_config(int(ctx["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404

    _activate_store_session(cfg)
    from app.client_request import capture_client_context
    from app.routes_work_card import _submit_work_card
    from app.ergani_env import client_for_store

    client_ctx = capture_client_context("telegram_retro")

    ev = (event or "").strip()
    if ev not in ("check_in", "check_out"):
        return {"success": False, "error": "Μη έγκυρο event"}, 400
    ref = (reference_date or ctx.get("reference_date_iso") or "").strip()[:10]
    rt = _normalize_hour(retro_time or ctx.get("retro_time") or "")
    if not ref or not rt:
        return {"success": False, "error": "Λείπουν ημερομηνία ή ώρα"}, 400

    bearer = session.get("ergani_bearer")
    if not bearer:
        return {"success": False, "error": "Αποτυχία σύνδεσης Ergani"}, 502

    client = client_for_store(cfg)
    body = {
        "employee_afm": ctx.get("employee_afm"),
        "eponymo": ctx.get("eponymo"),
        "onoma": ctx.get("onoma"),
        "event": ev,
        "reference_date": ref,
        "event_at": f"{ref}T{rt}:00",
    }
    if aitiologia:
        body["aitiologia"] = aitiologia
    body["source"] = "telegram_retro"
    resp, status = _submit_work_card(
        body=body,
        erg_s=str(cfg.get("employer_afm") or ""),
        aa_s=str(cfg.get("branch_aa") or "0"),
        bearer=str(bearer),
        api_base_url=client.base_url,
        client_ip=client_ctx.get("client_ip"),
        client_device=client_ctx.get("client_device"),
        store_id=int(ctx["store_id"]),
    )
    data = resp.get_json() if hasattr(resp, "get_json") else {}
    if status == 200 and data.get("success"):
        from app.repo_card import card_event_exists
        from app.work_card_payload import f_type_from_event

        resolved_type = f_type_from_event(ev, None)
        if card_event_exists(str(ctx.get("employee_afm") or ""), ref, resolved_type):
            if row:
                mark_token_used(token_id, retro_time=rt)
            clear_retro_hit_session()
            from app.scheduled_sync import enqueue_sync_store_today_after_card

            sync_triggered = enqueue_sync_store_today_after_card(cfg, work_date_iso=ref)
            data = {
                **(data or {}),
                "sync_triggered": sync_triggered,
            }
        else:
            data = {
                **(data or {}),
                "success": False,
                "error": (
                    "Η υποβολή στο Ergani φάνηκε επιτυχής αλλά δεν αποθηκεύτηκε στη βάση — "
                    "δοκιμάστε ξανά ή ελέγξτε τα καταγραφές."
                ),
            }
            status = 502
    return data or {"success": False}, status


def _normalize_hour(value: str) -> str:
    m = re.match(r"^(\d{1,2}):(\d{2})", (value or "").strip())
    if not m:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"


from app.public_urls import ui_public_url, ui_relative_path


def build_retro_hit_redirect_url(token: str | None = None) -> str:
    """Σχετική διαδρομή — μετά PIN μένει στο ίδιο host."""
    return ui_relative_path("/ui/retro-hit", token=token)


def build_telegram_hit_public_url(token: str) -> str:
    return ui_public_url("/ui/telegram-hit", token=token)


def punch_preview(token: str) -> tuple[dict[str, Any] | None, str | None]:
    row = get_punch_token_row(token)
    ok, err = token_is_valid(row)
    if not ok:
        return None, err
    assert row is not None
    event = row.get("card_event") or "check_in"
    event_label = "είσοδο" if event == "check_in" else "έξοδο"
    name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
    return {
        "store_name": row.get("store_name"),
        "employee_name": name or row.get("employee_afm"),
        "employee_afm": row.get("employee_afm"),
        "work_date": row.get("work_date_ergani"),
        "retro_time": row.get("retro_time"),
        "card_event": event,
        "card_event_label": event_label,
        "recipient_name": row.get("recipient_name"),
        "notification_kind": "missing_past",
    }, None


def _activate_store_session(cfg: dict[str, Any]) -> str | None:
    """Ενεργό κατάστημα + bearer Ergani για σελίδα ψηφιακής κάρτας."""
    from app.ergani_env import api_login_credentials, client_for_store
    from app.http_helpers import json_or_text

    session["active_store_id"] = int(cfg["id"])
    session["employer_afm"] = str(cfg.get("employer_afm") or "")
    session["branch_aa"] = str(cfg.get("branch_aa") or "0")
    session["ergani_env"] = cfg.get("ergani_env")
    try:
        client = client_for_store(cfg)
        api_user, api_pwd, api_ut = api_login_credentials(cfg)
        resp = client.authenticate(api_user, api_pwd, api_ut)
        payload = json_or_text(resp)
        if resp.ok and isinstance(payload, dict):
            token = str(payload.get("accessToken") or "").strip()
            if token:
                session["ergani_bearer"] = token
                return token
    except Exception:
        pass
    session.pop("ergani_bearer", None)
    return None


def confirm_punch_with_pin(token: str, pin: str) -> tuple[dict[str, Any], int]:
    row = get_punch_token_row(token)
    ok, err = token_is_valid(row)
    if not ok or not row:
        return {"success": False, "error": err or "Μη έγκυρο token"}, 400

    if not verify_notify_pin_for_recipient(
        store_id=int(row["store_id"]),
        mobile=row.get("mobile"),
        pin=str(pin or "").strip(),
        pin_hash=row.get("notify_pin_hash"),
        pin_plain=row.get("notify_pin"),
    ):
        attempts = increment_pin_attempts(int(row["id"]))
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
    mark_pin_verified(int(row["id"]))
    _store_punch_session(row)
    redirect = build_retro_hit_redirect_url(token)
    event = row.get("card_event") or "check_in"
    event_label = "είσοδο" if event == "check_in" else "έξοδο"
    return {
        "success": True,
        "redirect": redirect,
        "detail": (
            f"Μετάβαση σε προγενέστερη καταχώρηση — {event_label} "
            f"({row.get('work_date_ergani') or ''})."
        ),
    }, 200


def send_missing_punch_notifications(
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
    public_base_url: str,
) -> dict[str, Any]:
    from app.email_notify import EmailNotConfigured, send_notification_email
    from app.repo_notify_recipients import (
        list_deliverable_recipients,
        list_email_deliverable_recipients,
    )
    from app.repo_telegram_punch import create_punch_token
    from app.telegram_notify import (
        TelegramNotConfigured,
        format_missing_punch_notification,
        send_telegram_message,
    )

    action = resolve_missing_punch_action(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        work_date=work_date,
        hour_from=hour_from,
        hour_to=hour_to,
    )
    recipients = list_deliverable_recipients(store_id)
    email_recipients = list_email_deliverable_recipients(store_id)
    if not action:
        skipped = missing_punch_notify_skip_reason(
            employee_afm=employee_afm,
            work_date=work_date,
            hour_from=hour_from,
            hour_to=hour_to,
        )
        return {
            "sent": 0,
            "total": len(recipients) + len(email_recipients),
            "errors": [],
            "action": None,
            "skipped": skipped or "no_action",
        }
    sent = 0
    errors: list[str] = []
    ref_iso = ergani_date_to_iso(work_date)

    for rec in recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
            continue
        hit_url = None
        if action and (rec.get("notify_pin_hash") or "").strip():
            try:
                token = create_punch_token(
                    recipient_id=int(rec["id"]),
                    store_id=store_id,
                    employee_afm=employee_afm,
                    eponymo=eponymo,
                    onoma=onoma,
                    work_date_ergani=work_date,
                    reference_date_iso=ref_iso,
                    card_event=action["card_event"],
                    retro_time=action.get("retro_time") or "",
                )
                hit_url = build_telegram_hit_public_url(token)
            except Exception as ex:
                errors.append(f"{rec.get('name')}: token — {ex}")
        text = format_missing_punch_notification(
            store_name=store_name,
            employee_afm=employee_afm,
            eponymo=eponymo,
            onoma=onoma,
            work_date=work_date,
            hour_from=hour_from,
            hour_to=hour_to,
            retro_time=action.get("retro_time") if action else None,
            card_event=action["card_event"] if action else None,
            hit_url=hit_url,
            has_pin=bool((rec.get("notify_pin_hash") or "").strip()),
        )
        try:
            send_telegram_message(chat_id, text)
            sent += 1
        except TelegramNotConfigured:
            errors.append(f"Telegram {rec.get('name')}: λείπει TELEGRAM_BOT_TOKEN")
        except Exception as ex:
            errors.append(f"Telegram {rec.get('name')}: {ex}")

    employee_name = f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip()
    if action.get("card_event") == "check_in":
        defect = "Ελλιπές χτύπημα εισόδου"
    elif action.get("card_event") == "check_out":
        defect = "Ελλιπές χτύπημα εξόδου"
    else:
        defect = "Ελλιπές χτύπημα κάρτας"
    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        hit_url = None
        has_pin = bool((rec.get("notify_pin_hash") or "").strip())
        if has_pin:
            try:
                token = create_punch_token(
                    recipient_id=int(rec["id"]),
                    store_id=store_id,
                    employee_afm=employee_afm,
                    eponymo=eponymo,
                    onoma=onoma,
                    work_date_ergani=work_date,
                    reference_date_iso=ref_iso,
                    card_event=action["card_event"],
                    retro_time=action.get("retro_time") or "",
                )
                hit_url = build_telegram_hit_public_url(token)
            except Exception as ex:
                errors.append(f"Email {rec.get('name')}: token — {ex}")
        try:
            send_notification_email(
                email,
                f"erganiOS — {defect}",
                title=defect,
                preheader=f"{employee_name or employee_afm} · {work_date}",
                store_name=store_name,
                employee_name=employee_name,
                employee_afm=employee_afm,
                work_date=work_date,
                problem=f"Υπάρχει {defect.lower()} για τον εργαζόμενο.",
                details=[
                    ("Προτεινόμενη ώρα", action.get("retro_time") or "—"),
                    ("Ενέργεια", "Άνοιγμα προγενέστερης καταχώρησης" if hit_url else "Απαιτείται PIN λήπτη"),
                ],
                action_url=hit_url,
                action_label="Άνοιγμα καταχώρησης",
                footer_note=(
                    "Το άνοιγμα της ενέργειας απαιτεί τον προσωπικό PIN του λήπτη."
                    if hit_url
                    else "Δεν δημιουργήθηκε σύνδεσμος επειδή δεν έχει οριστεί PIN για τον λήπτη."
                ),
            )
            sent += 1
        except EmailNotConfigured as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")
        except Exception as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")

    return {
        "sent": sent,
        "total": len(recipients) + len(email_recipients),
        "errors": errors,
        "action": action,
    }
