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
from app.notify_pin import is_valid_notify_pin
from app.telegram_punch_service import (
    confirm_punch_with_pin,
    get_retro_hit_context,
    punch_preview,
    send_missing_punch_notifications,
    submit_retro_hit_from_session,
)
from app.today_alert_service import (
    confirm_today_hit_with_pin,
    get_today_action_context,
    prepare_card_from_today_alert,
    send_today_punch_notifications,
    snooze_today_alert,
    submit_today_leave,
    today_hit_preview,
)

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
    if result.get("skipped") == "already_submitted":
        payload["success"] = False
        payload["error"] = (
            "Υπάρχει ήδη δήλωση κάρτας στη βάση για αυτό το χτύπημα — "
            "δεν αποστέλλεται ξανά ειδοποίηση."
        )
        return jsonify(payload), 400
    if result.get("skipped") and not ok:
        payload["success"] = False
        payload["error"] = "Δεν ορίστηκε ενέργεια ειδοποίησης για αυτή τη γραμμή."
        return jsonify(payload), 400
    if not ok and not result["total"]:
        payload["error"] = (
            "Δεν υπάρχουν λήπτες με συνδεδεμένο Telegram. "
            "Προσθέστε λήπτες στο κατάστημα και /start στο bot."
        )
    elif not ok:
        payload["error"] = "Η αποστολή απέτυχε για όλους τους λήπτες"
    return jsonify(payload), (200 if ok else 400)


@telegram_bp.post("/notify/today-punch")
def telegram_notify_today_punch():
    """Ειδοποίηση τύπου 2 — πρόβλημα τρέχουσας ημέρας."""
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
        result = send_today_punch_notifications(
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
            notify_kind=data.get("notify_kind"),
            public_base_url=Config.PUBLIC_BASE_URL,
        )
    except TelegramNotConfigured as ex:
        return jsonify({"error": str(ex)}), 400
    ok = result["sent"] > 0
    payload = {"success": ok, **result}
    if result.get("skipped") == "snoozed":
        payload["success"] = False
        payload["error"] = "Η ειδοποίηση είναι σε αναβολή (snooze) για αυτή την περίπτωση."
        return jsonify(payload), 400
    if result.get("skipped") in ("no_alert", "kind_mismatch"):
        payload["success"] = False
        payload["error"] = "Δεν ισχύει πλέον συνθήκη ειδοποίησης για αυτή τη γραμμή."
        return jsonify(payload), 400
    if not ok and not result["total"]:
        payload["error"] = (
            "Δεν υπάρχουν λήπτες με συνδεδεμένο Telegram. "
            "Προσθέστε λήπτες στο κατάστημα και /start στο bot."
        )
    elif not ok:
        payload["error"] = "Η αποστολή απέτυχε για όλους τους λήπτες"
    return jsonify(payload), (200 if ok else 400)


@telegram_bp.get("/today-hit/<token>")
def telegram_today_hit_preview(token: str):
    preview, err = today_hit_preview(token)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "preview": preview})


@telegram_bp.post("/today-hit/<token>/confirm")
def telegram_today_hit_confirm(token: str):
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "").strip()
    if not pin:
        return jsonify({"error": "Λείπει PIN"}), 400
    if not is_valid_notify_pin(pin):
        return jsonify({"error": "Ο PIN πρέπει να είναι ακριβώς 4 αριθμητικά ψηφία"}), 400
    result, status = confirm_today_hit_with_pin(token, pin)
    return jsonify(result), status


@telegram_bp.get("/today-action/context")
def telegram_today_action_context():
    from app.leave_types import LEAVE_TYPES

    token = str(request.args.get("t") or "").strip() or None
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return jsonify({"error": err or "Λήξη συνεδρίας"}), 401
    payload = {"ok": True, "context": ctx}
    if ctx.get("leave_eligible"):
        payload["leave_types"] = LEAVE_TYPES
    return jsonify(payload)


@telegram_bp.post("/today-action/snooze")
def telegram_today_action_snooze():
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip() or None
    result, status = snooze_today_alert(token=token)
    return jsonify(result), status


@telegram_bp.post("/today-action/card")
def telegram_today_action_card():
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip() or None
    result, status = prepare_card_from_today_alert(token=token)
    return jsonify(result), status


@telegram_bp.post("/today-action/leave")
def telegram_today_action_leave():
    data = request.get_json(silent=True) or {}
    leave_type = str(data.get("leave_type") or "").strip()
    if not leave_type:
        return jsonify({"error": "Λείπει leave_type"}), 400
    token = str(data.get("token") or "").strip() or None
    result, status = submit_today_leave(
        leave_type=leave_type,
        comments=data.get("comments"),
        token=token,
    )
    return jsonify(result), status


@telegram_bp.get("/hit/<token>")
@telegram_bp.get("/punch/<token>")
def telegram_hit_preview(token: str):
    preview, err = punch_preview(token)
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True, "preview": preview})


@telegram_bp.post("/hit/<token>/confirm")
@telegram_bp.post("/punch/<token>/confirm")
def telegram_hit_confirm(token: str):
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "").strip()
    if not pin:
        return jsonify({"error": "Λείπει PIN"}), 400
    if not is_valid_notify_pin(pin):
        return jsonify({"error": "Ο PIN πρέπει να είναι ακριβώς 4 αριθμητικά ψηφία"}), 400
    result, status = confirm_punch_with_pin(token, pin)
    return jsonify(result), status


@telegram_bp.get("/retro-hit/context")
def telegram_retro_hit_context():
    token = str(request.args.get("t") or "").strip() or None
    ctx, err = get_retro_hit_context(token=token)
    if err or not ctx:
        return jsonify({"error": err or "Λήξη συνεδρίας"}), 401
    return jsonify({"ok": True, "context": ctx})


@telegram_bp.post("/retro-hit/submit")
def telegram_retro_hit_submit():
    data = request.get_json(silent=True) or {}
    event = str(data.get("event") or "").strip()
    reference_date = str(data.get("reference_date") or "").strip()
    retro_time = str(data.get("retro_time") or "").strip()
    aitiologia = str(data.get("aitiologia") or "001").strip() or "001"
    token = str(data.get("token") or "").strip() or None
    result, status = submit_retro_hit_from_session(
        event=event,
        reference_date=reference_date,
        retro_time=retro_time,
        aitiologia=aitiologia,
        token=token,
    )
    return jsonify(result), status
