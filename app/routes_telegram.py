"""Telegram Bot — webhook σύνδεσης ληπτών + δοκιμαστική αποστολή."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app import repo_store as repo
from app.repo_notify_recipients import link_telegram_chat_by_mobile, normalize_mobile
from app.telegram_notify import TelegramNotConfigured, notify_store_recipients, send_telegram_message

telegram_bp = Blueprint("telegram", __name__, url_prefix="/api/telegram")


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
        try:
            send_telegram_message(
                str(chat_id),
                "erganiOS: στείλτε /start ΑΡΙΘΜΟΣ_ΚΙΝΗΤΟΥ (π.χ. /start 6912345678) "
                "για σύνδεση ειδοποιήσεων.",
            )
        except TelegramNotConfigured:
            pass
        return jsonify({"ok": True})

    mobile = normalize_mobile(parts[1])
    linked = link_telegram_chat_by_mobile(mobile, str(chat_id))
    try:
        if linked:
            send_telegram_message(
                str(chat_id),
                f"Συνδέθηκε επιτυχώς ({linked} καταχώρηση/σεις). Θα λαμβάνετε ειδοποιήσεις erganiOS.",
            )
        else:
            send_telegram_message(
                str(chat_id),
                "Το κινητό δεν βρέθηκε σε λήπτες καταστήματος. "
                "Προσθέστε πρώτα όνομα και αριθμό στην επεξεργασία καταστήματος.",
            )
    except TelegramNotConfigured:
        pass
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
