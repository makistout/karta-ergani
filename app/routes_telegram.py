"""Telegram Bot — webhook σύνδεσης ληπτών + δοκιμαστική αποστολή."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from app import repo_store as repo
from app.repo_notify_recipients import link_telegram_chat_by_mobile, normalize_mobile
from config import Config
from app.telegram_notify import (
    TelegramNotConfigured,
    notify_store_recipients,
    send_telegram_message,
)
from app.telegram_punch_service import confirm_punch_with_pin, punch_preview, send_missing_punch_notifications

telegram_bp = Blueprint("telegram", __name__, url_prefix="/api/telegram")
logger = logging.getLogger(__name__)


def _reply_chat(chat_id: str, text: str) -> None:
    """Απάντηση στον χρήστη — πάντα αθόρυβα σε σφάλμα (το webhook πρέπει να επιστρέφει 200)."""
    try:
        send_telegram_message(str(chat_id), text)
    except TelegramNotConfigured:
        logger.warning("Telegram webhook: bot token not configured")
    except Exception:
        logger.exception("Telegram webhook: failed to reply chat_id=%s", chat_id)


@telegram_bp.post("/webhook")
def telegram_webhook():
    """Ο λήπτης στέλνει: /start 6912345678 → σύνδεση chat_id με κινητό στη βάση."""
    update = request.get_json(silent=True) or {}
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = str(message.get("text") or "").strip()
    if not chat_id or not text.startswith("/start"):
        return jsonify({"ok": True})

    parts = text.split()
    if len(parts) < 2:
        _reply_chat(
            str(chat_id),
            "erganiOS: στείλτε /start ΑΡΙΘΜΟΣ_ΚΙΝΗΤΟΥ (π.χ. /start 6912345678) "
            "για σύνδεση ειδοποιήσεων.",
        )
        return jsonify({"ok": True})

    mobile = normalize_mobile(parts[1])
    linked = link_telegram_chat_by_mobile(mobile, str(chat_id))
    if linked:
        _reply_chat(
            str(chat_id),
            f"Συνδέθηκε επιτυχώς ({linked} καταχώρηση/σεις). Θα λαμβάνετε ειδοποιήσεις erganiOS.",
        )
    else:
        _reply_chat(
            str(chat_id),
            "Το κινητό δεν βρέθηκε σε λήπτες καταστήματος. "
            "Προσθέστε πρώτα όνομα και αριθμό στην επεξεργασία καταστήματος.",
        )
    return jsonify({"ok": True, "linked": linked})


@telegram_bp.post("/test/<int:store_id>")
def telegram_test_store(store_id: int):
    cfg = repo.get_store_config(store_id)
    if not cfg:
        return jsonify({"error": "Δεν βρέθηκε κατάστημα"}), 404
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip() or (
        f"Δοκιμαστική ειδοποίηση erganiOS — {cfg.get('name') or store_id}"
    )
    try:
        result = notify_store_recipients(store_id, text)
    except TelegramNotConfigured as ex:
        return jsonify({"error": str(ex)}), 400
    return jsonify({"success": result["sent"] > 0, **result})


@telegram_bp.post("/notify/missing-punch")
def telegram_notify_missing_punch():
    """Ειδοποίηση ληπτών για ελλιπή είσοδο/έξοδο (σελίδα ελλειπών χτυπημάτων)."""
    from app.http_helpers import resolve_active_store

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    data = request.get_json(silent=True) or {}
    employee_afm = str(data.get("employee_afm") or "").strip()
    work_date = str(data.get("work_date") or "").strip()
    if not employee_afm or not work_date:
        return jsonify({"error": "Λείπουν employee_afm ή work_date"}), 400
    try:
        result = send_missing_punch_notifications(
            store_id=int(ctx["id"]),
            store_name=str(ctx.get("name") or ""),
            employer_afm=str(ctx.get("employer_afm") or ""),
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=employee_afm,
            eponymo=data.get("eponymo"),
            onoma=data.get("onoma"),
            work_date=work_date,
            hour_from=data.get("hour_from"),
            hour_to=data.get("hour_to"),
            public_base_url=Config.PUBLIC_BASE_URL,
        )
    except TelegramNotConfigured as ex:
        return jsonify({"error": str(ex)}), 400
    ok = result["sent"] > 0
    payload = {"success": ok, **result}
    if not ok and not result["total"]:
        payload["error"] = (
            "Δεν υπάρχουν λήπτες με συνδεδεμένο Telegram. "
            "Προσθέστε λήπτες στο κατάστημα και /start στο bot."
        )
    elif not ok:
        payload["error"] = "Η αποστολή απέτυχε για όλους τους λήπτες"
    return jsonify(payload), (200 if ok else 400)


@telegram_bp.get("/punch/<token>")
def telegram_punch_preview(token: str):
    preview, err = punch_preview(token)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "preview": preview})


@telegram_bp.post("/punch/<token>/confirm")
def telegram_punch_confirm(token: str):
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "").strip()
    if not pin:
        return jsonify({"error": "Λείπει PIN"}), 400
    result, status = confirm_punch_with_pin(token, pin)
    return jsonify(result), status
