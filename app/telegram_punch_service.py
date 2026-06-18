"""Εκτέλεση χτυπήματος κάρτας από token Telegram + PIN."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app import repo_store as repo
from app.ergani_env import api_login_credentials, client_for_store
from app.notify_pin import verify_notify_pin
from app.repo_notify_recipients import normalize_mobile
from app.repo_telegram_punch import (
    get_punch_token_row,
    increment_pin_attempts,
    mark_token_used,
    token_is_valid,
)
from app.repo_work_log import enrich_work_log_rows_with_card_punch
from app.routes_work_card import _submit_work_card
from app.work_card_payload import tz_athens

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
    """Επιστρέφει card_event + retro_time από ψηφιακό ωράριο."""
    row = {
        "employee_afm": employee_afm,
        "work_date": work_date,
        "hour_from": hour_from,
        "hour_to": hour_to,
    }
    enrich_work_log_rows_with_card_punch([row], employer_afm, branch_aa)
    if not row.get("needs_card_punch") or not row.get("retro_time"):
        return None
    return {
        "card_event": str(row.get("card_event") or "check_in"),
        "retro_time": str(row.get("retro_time") or "").strip(),
    }


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
    }, None


def _bearer_for_store(cfg: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        client = client_for_store(cfg)
        api_user, api_pwd, api_ut = api_login_credentials(cfg)
        resp = client.authenticate(api_user, api_pwd, api_ut)
        from app.http_helpers import json_or_text

        payload = json_or_text(resp)
        if resp.ok and isinstance(payload, dict):
            token = str(payload.get("accessToken") or "").strip()
            if token:
                return token, None
        return None, "Αποτυχία αυθεντικοποίησης Ergani"
    except Exception as ex:
        return None, str(ex)


def confirm_punch_with_pin(token: str, pin: str) -> tuple[dict[str, Any], int]:
    row = get_punch_token_row(token)
    ok, err = token_is_valid(row)
    if not ok or not row:
        return {"success": False, "error": err or "Μη έγκυρο token"}, 400

    if not verify_notify_pin(
        store_id=int(row["store_id"]),
        mobile=normalize_mobile(row.get("mobile")),
        pin=str(pin or "").strip(),
        pin_hash=row.get("notify_pin_hash"),
    ):
        attempts = increment_pin_attempts(int(row["id"]))
        if attempts >= 5:
            return {"success": False, "error": "Λάθος PIN — ο σύνδεσμος κλειδώθηκε"}, 403
        return {"success": False, "error": "Λάθος PIN"}, 401

    cfg = repo.get_store_config(int(row["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404

    bearer, auth_err = _bearer_for_store(cfg)
    if not bearer:
        return {"success": False, "error": auth_err or "Auth failed"}, 502

    ref_iso = row.get("reference_date_iso") or ergani_date_to_iso(
        str(row.get("work_date_ergani") or "")
    )
    retro_time = str(row.get("retro_time") or "").strip()
    card_event = str(row.get("card_event") or "check_in")
    body = {
        "employee_afm": row.get("employee_afm"),
        "eponymo": row.get("eponymo"),
        "onoma": row.get("onoma"),
        "event": card_event,
        "reference_date": ref_iso,
        "event_at": f"{ref_iso}T{retro_time}:00",
        "aitiologia": RETRO_AITIOLOGIA,
    }

    client = client_for_store(cfg)
    resp, status = _submit_work_card(
        body=body,
        erg_s=str(cfg.get("employer_afm") or ""),
        aa_s=str(cfg.get("branch_aa") or "0"),
        bearer=bearer,
        api_base_url=client.base_url,
    )
    data = resp.get_json() if hasattr(resp, "get_json") else {}
    if status == 200 and data.get("success"):
        mark_token_used(int(row["id"]))
    return data or {"success": False}, status


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
    from app.repo_notify_recipients import list_deliverable_recipients
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
    sent = 0
    errors: list[str] = []
    ref_iso = ergani_date_to_iso(work_date)

    for rec in recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
            continue
        punch_url = None
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
                    retro_time=action["retro_time"],
                )
                punch_url = f"{public_base_url.rstrip('/')}/ui/telegram-punch?t={token}"
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
            retro_time=action["retro_time"] if action else None,
            card_event=action["card_event"] if action else None,
            punch_url=punch_url,
            has_pin=bool((rec.get("notify_pin_hash") or "").strip()),
        )
        try:
            send_telegram_message(chat_id, text)
            sent += 1
        except TelegramNotConfigured:
            raise
        except Exception as ex:
            errors.append(f"{rec.get('name')}: {ex}")

    return {"sent": sent, "total": len(recipients), "errors": errors, "action": action}
