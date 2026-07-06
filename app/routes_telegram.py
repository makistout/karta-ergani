"""Telegram Bot β€” webhook ΟƒΟΞ½Ξ΄ΞµΟƒΞ·Ο‚ Ξ»Ξ·Ο€Ο„ΟΞ½ + Ξ΄ΞΏΞΊΞΉΞΌΞ±ΟƒΟ„ΞΉΞΊΞ® Ξ±Ο€ΞΏΟƒΟ„ΞΏΞ»Ξ®."""

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
from app.audit_log import record_audit_event
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


def _audit_notification_open(action: str, *, token: str | None, ok: bool, error: str | None = None) -> None:
    actor = None
    if token:
        try:
            from app.repo_today_alert import get_today_alert_token_row

            row = get_today_alert_token_row(token)
            if row:
                name = str(row.get("recipient_name") or "").strip()
                mobile = str(row.get("mobile") or "").strip()
                actor = {
                    "recipient_id": row.get("recipient_id"),
                    "name": name or mobile or None,
                    "mobile": mobile or None,
                    "store_id": row.get("store_id"),
                    "store_name": row.get("store_name"),
                }
        except Exception:
            actor = None
    record_audit_event(
        action=action,
        success=ok,
        http_status=200 if ok else 400,
        entity_type="telegram_action",
        entity_id=None,
        details={
            "source": "notification_link",
            "token": token,
            "error": error,
            "notification_actor": actor,
        },
    )


def _reply_chat(chat_id: str, text: str) -> None:
    """Ξ‘Ο€Ξ¬Ξ½Ο„Ξ·ΟƒΞ· ΟƒΟ„ΞΏΞ½ Ο‡ΟΞ®ΟƒΟ„Ξ· β€” Ο€Ξ¬Ξ½Ο„Ξ± Ξ±ΞΈΟΟΟ…Ξ²Ξ± ΟƒΞµ ΟƒΟ†Ξ¬Ξ»ΞΌΞ± (Ο„ΞΏ webhook Ο€ΟΞ­Ο€ΞµΞΉ Ξ½Ξ± ΞµΟ€ΞΉΟƒΟ„ΟΞ­Ο†ΞµΞΉ 200)."""
    try:
        send_telegram_message(str(chat_id), text)
    except TelegramNotConfigured:
        logger.warning("Telegram webhook: bot token not configured")
    except Exception:
        logger.exception("Telegram webhook: failed to reply chat_id=%s", chat_id)


@telegram_bp.post("/webhook")
def telegram_webhook():
    """Ξ Ξ»Ξ®Ο€Ο„Ξ·Ο‚ ΟƒΟ„Ξ­Ξ»Ξ½ΞµΞΉ: /start 6912345678 β†’ ΟƒΟΞ½Ξ΄ΞµΟƒΞ· chat_id ΞΌΞµ ΞΊΞΉΞ½Ξ·Ο„Ο ΟƒΟ„Ξ· Ξ²Ξ¬ΟƒΞ·."""
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
            "erganiOS: ΟƒΟ„ΞµΞ―Ξ»Ο„Ξµ /start Ξ‘Ξ΅Ξ™ΞΞΞΞ£_ΞΞ™ΞΞ—Ξ¤ΞΞ¥ (Ο€.Ο‡. /start 6912345678) "
            "Ξ³ΞΉΞ± ΟƒΟΞ½Ξ΄ΞµΟƒΞ· ΞµΞΉΞ΄ΞΏΟ€ΞΏΞΉΞ®ΟƒΞµΟ‰Ξ½.",
        )
        return jsonify({"ok": True})

    mobile = normalize_mobile(parts[1])
    linked = link_telegram_chat_by_mobile(mobile, str(chat_id))
    if linked:
        _reply_chat(
            str(chat_id),
            f"Ξ£Ο…Ξ½Ξ΄Ξ­ΞΈΞ·ΞΊΞµ ΞµΟ€ΞΉΟ„Ο…Ο‡ΟΟ‚ ({linked} ΞΊΞ±Ο„Ξ±Ο‡ΟΟΞ·ΟƒΞ·/ΟƒΞµΞΉΟ‚). ΞΞ± Ξ»Ξ±ΞΌΞ²Ξ¬Ξ½ΞµΟ„Ξµ ΞµΞΉΞ΄ΞΏΟ€ΞΏΞΉΞ®ΟƒΞµΞΉΟ‚ erganiOS.",
        )
    else:
        _reply_chat(
            str(chat_id),
            "Ξ¤ΞΏ ΞΊΞΉΞ½Ξ·Ο„Ο Ξ΄ΞµΞ½ Ξ²ΟΞ­ΞΈΞ·ΞΊΞµ ΟƒΞµ Ξ»Ξ®Ο€Ο„ΞµΟ‚ ΞΊΞ±Ο„Ξ±ΟƒΟ„Ξ®ΞΌΞ±Ο„ΞΏΟ‚. "
            "Ξ ΟΞΏΟƒΞΈΞ­ΟƒΟ„Ξµ Ο€ΟΟΟ„Ξ± ΟΞ½ΞΏΞΌΞ± ΞΊΞ±ΞΉ Ξ±ΟΞΉΞΈΞΌΟ ΟƒΟ„Ξ·Ξ½ ΞµΟ€ΞµΞΎΞµΟΞ³Ξ±ΟƒΞ―Ξ± ΞΊΞ±Ο„Ξ±ΟƒΟ„Ξ®ΞΌΞ±Ο„ΞΏΟ‚.",
        )
    return jsonify({"ok": True, "linked": linked})


@telegram_bp.post("/test/<int:store_id>")
def telegram_test_store(store_id: int):
    cfg = repo.get_store_config(store_id)
    if not cfg:
        return jsonify({"error": "Ξ”ΞµΞ½ Ξ²ΟΞ­ΞΈΞ·ΞΊΞµ ΞΊΞ±Ο„Ξ¬ΟƒΟ„Ξ·ΞΌΞ±"}), 404
    data = request.get_json(silent=True) or {}
    text = (data.get("message") or "").strip() or (
        f"Ξ”ΞΏΞΊΞΉΞΌΞ±ΟƒΟ„ΞΉΞΊΞ® ΞµΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ· erganiOS β€” {cfg.get('name') or store_id}"
    )
    try:
        result = notify_store_recipients(store_id, text)
    except TelegramNotConfigured as ex:
        return jsonify({"error": str(ex)}), 400
    return jsonify({"success": result["sent"] > 0, **result})


@telegram_bp.post("/notify/missing-punch")
def telegram_notify_missing_punch():
    """Ξ•ΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ· Ξ»Ξ·Ο€Ο„ΟΞ½ Ξ³ΞΉΞ± ΞµΞ»Ξ»ΞΉΟ€Ξ® ΞµΞ―ΟƒΞΏΞ΄ΞΏ/Ξ­ΞΎΞΏΞ΄ΞΏ (ΟƒΞµΞ»Ξ―Ξ΄Ξ± ΞµΞ»Ξ»ΞµΞΉΟ€ΟΞ½ Ο‡Ο„Ο…Ο€Ξ·ΞΌΞ¬Ο„Ο‰Ξ½)."""
    from app.http_helpers import resolve_active_store

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Ξ•Ο€ΞΉΞ»Ξ­ΞΎΟ„Ξµ Ο€ΟΟΟ„Ξ± ΞΊΞ±Ο„Ξ¬ΟƒΟ„Ξ·ΞΌΞ±"}), 400
    data = request.get_json(silent=True) or {}
    employee_afm = str(data.get("employee_afm") or "").strip()
    work_date = str(data.get("work_date") or "").strip()
    if not employee_afm or not work_date:
        return jsonify({"error": "Ξ›ΞµΞ―Ο€ΞΏΟ…Ξ½ employee_afm Ξ® work_date"}), 400
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
            "Ξ¥Ο€Ξ¬ΟΟ‡ΞµΞΉ Ξ®Ξ΄Ξ· Ξ΄Ξ®Ξ»Ο‰ΟƒΞ· ΞΊΞ¬ΟΟ„Ξ±Ο‚ ΟƒΟ„Ξ· Ξ²Ξ¬ΟƒΞ· Ξ³ΞΉΞ± Ξ±Ο…Ο„Ο Ο„ΞΏ Ο‡Ο„ΟΟ€Ξ·ΞΌΞ± β€” "
            "Ξ΄ΞµΞ½ Ξ±Ο€ΞΏΟƒΟ„Ξ­Ξ»Ξ»ΞµΟ„Ξ±ΞΉ ΞΎΞ±Ξ½Ξ¬ ΞµΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ·."
        )
        return jsonify(payload), 400
    if result.get("skipped") and not ok:
        payload["success"] = False
        payload["error"] = "Ξ”ΞµΞ½ ΞΏΟΞ―ΟƒΟ„Ξ·ΞΊΞµ ΞµΞ½Ξ­ΟΞ³ΞµΞΉΞ± ΞµΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ·Ο‚ Ξ³ΞΉΞ± Ξ±Ο…Ο„Ξ® Ο„Ξ· Ξ³ΟΞ±ΞΌΞΌΞ®."
        return jsonify(payload), 400
    if not ok and not result["total"]:
        payload["error"] = (
            "Ξ”ΞµΞ½ Ο…Ο€Ξ¬ΟΟ‡ΞΏΟ…Ξ½ Ξ»Ξ®Ο€Ο„ΞµΟ‚ ΞΌΞµ ΟƒΟ…Ξ½Ξ΄ΞµΞ΄ΞµΞΌΞ­Ξ½ΞΏ Telegram. "
            "Ξ ΟΞΏΟƒΞΈΞ­ΟƒΟ„Ξµ Ξ»Ξ®Ο€Ο„ΞµΟ‚ ΟƒΟ„ΞΏ ΞΊΞ±Ο„Ξ¬ΟƒΟ„Ξ·ΞΌΞ± ΞΊΞ±ΞΉ /start ΟƒΟ„ΞΏ bot."
        )
    elif not ok:
        payload["error"] = "Ξ— Ξ±Ο€ΞΏΟƒΟ„ΞΏΞ»Ξ® Ξ±Ο€Ξ­Ο„Ο…Ο‡Ξµ Ξ³ΞΉΞ± ΟΞ»ΞΏΟ…Ο‚ Ο„ΞΏΟ…Ο‚ Ξ»Ξ®Ο€Ο„ΞµΟ‚"
    return jsonify(payload), (200 if ok else 400)


@telegram_bp.post("/notify/today-punch")
def telegram_notify_today_punch():
    """Ξ•ΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ· Ο„ΟΟ€ΞΏΟ… 2 β€” Ο€ΟΟΞ²Ξ»Ξ·ΞΌΞ± Ο„ΟΞ­Ο‡ΞΏΟ…ΟƒΞ±Ο‚ Ξ·ΞΌΞ­ΟΞ±Ο‚."""
    from app.http_helpers import resolve_active_store

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Ξ•Ο€ΞΉΞ»Ξ­ΞΎΟ„Ξµ Ο€ΟΟΟ„Ξ± ΞΊΞ±Ο„Ξ¬ΟƒΟ„Ξ·ΞΌΞ±"}), 400
    data = request.get_json(silent=True) or {}
    employee_afm = str(data.get("employee_afm") or "").strip()
    work_date = str(data.get("work_date") or "").strip()
    if not employee_afm or not work_date:
        return jsonify({"error": "Ξ›ΞµΞ―Ο€ΞΏΟ…Ξ½ employee_afm Ξ® work_date"}), 400
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
        payload["error"] = "Ξ— ΞµΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ· ΞµΞ―Ξ½Ξ±ΞΉ ΟƒΞµ Ξ±Ξ½Ξ±Ξ²ΞΏΞ»Ξ® (snooze) Ξ³ΞΉΞ± Ξ±Ο…Ο„Ξ® Ο„Ξ·Ξ½ Ο€ΞµΟΞ―Ο€Ο„Ο‰ΟƒΞ·."
        return jsonify(payload), 400
    if result.get("skipped") in ("no_alert", "kind_mismatch"):
        payload["success"] = False
        payload["error"] = "Ξ”ΞµΞ½ ΞΉΟƒΟ‡ΟΞµΞΉ Ο€Ξ»Ξ­ΞΏΞ½ ΟƒΟ…Ξ½ΞΈΞ®ΞΊΞ· ΞµΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ·Ο‚ Ξ³ΞΉΞ± Ξ±Ο…Ο„Ξ® Ο„Ξ· Ξ³ΟΞ±ΞΌΞΌΞ®."
        return jsonify(payload), 400
    if not ok and not result["total"]:
        payload["error"] = (
            "Ξ”ΞµΞ½ Ο…Ο€Ξ¬ΟΟ‡ΞΏΟ…Ξ½ Ξ»Ξ®Ο€Ο„ΞµΟ‚ ΞΌΞµ ΟƒΟ…Ξ½Ξ΄ΞµΞ΄ΞµΞΌΞ­Ξ½ΞΏ Telegram. "
            "Ξ ΟΞΏΟƒΞΈΞ­ΟƒΟ„Ξµ Ξ»Ξ®Ο€Ο„ΞµΟ‚ ΟƒΟ„ΞΏ ΞΊΞ±Ο„Ξ¬ΟƒΟ„Ξ·ΞΌΞ± ΞΊΞ±ΞΉ /start ΟƒΟ„ΞΏ bot."
        )
    elif not ok:
        payload["error"] = "Ξ— Ξ±Ο€ΞΏΟƒΟ„ΞΏΞ»Ξ® Ξ±Ο€Ξ­Ο„Ο…Ο‡Ξµ Ξ³ΞΉΞ± ΟΞ»ΞΏΟ…Ο‚ Ο„ΞΏΟ…Ο‚ Ξ»Ξ®Ο€Ο„ΞµΟ‚"
    return jsonify(payload), (200 if ok else 400)


@telegram_bp.post("/notify/schedule-fix")
def telegram_notify_schedule_fix():
    """Ξ•ΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ· Telegram β€” ΟΞµΟ€Ο/Ξ±Ξ½Ξ¬Ο€Ξ±Ο…ΟƒΞ· ΞΌΞµ ΞΊΞ±Ο„Ξ±Ξ³ΟΞ±Ο†Ξ® ΞµΟΞ³Ξ±ΟƒΞ―Ξ±Ο‚ (WTODaily)."""
    from app.http_helpers import resolve_active_store
    from app.today_alert_service import send_wto_schedule_notifications

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Ξ•Ο€ΞΉΞ»Ξ­ΞΎΟ„Ξµ Ο€ΟΟΟ„Ξ± ΞΊΞ±Ο„Ξ¬ΟƒΟ„Ξ·ΞΌΞ±"}), 400
    data = request.get_json(silent=True) or {}
    employee_afm = str(data.get("employee_afm") or "").strip()
    work_date = str(data.get("work_date") or "").strip()
    notify_kind = str(data.get("notify_kind") or "rest_with_card").strip()
    if not employee_afm or not work_date:
        return jsonify({"error": "Ξ›ΞµΞ―Ο€ΞΏΟ…Ξ½ employee_afm Ξ® work_date"}), 400
    try:
        result = send_wto_schedule_notifications(
            store_id=int(ctx["id"]),
            store_name=str(ctx.get("name") or ""),
            employer_afm=str(ctx.get("employer_afm") or ""),
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=employee_afm,
            eponymo=data.get("eponymo"),
            onoma=data.get("onoma"),
            work_date=work_date,
            notify_kind=notify_kind,
            hour_from=data.get("hour_from"),
            hour_to=data.get("hour_to"),
            public_base_url=Config.PUBLIC_BASE_URL,
        )
    except TelegramNotConfigured as ex:
        return jsonify({"error": str(ex)}), 400
    ok = result["sent"] > 0
    payload = {"success": ok, **result}
    if result.get("skipped") == "snoozed":
        payload["success"] = False
        payload["error"] = "Ξ— ΞµΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ· ΞµΞ―Ξ½Ξ±ΞΉ ΟƒΞµ Ξ±Ξ½Ξ±Ξ²ΞΏΞ»Ξ® (snooze) Ξ³ΞΉΞ± Ξ±Ο…Ο„Ξ® Ο„Ξ·Ξ½ Ο€ΞµΟΞ―Ο€Ο„Ο‰ΟƒΞ·."
        return jsonify(payload), 400
    if result.get("skipped") in ("no_alert", "invalid_kind"):
        payload["success"] = False
        payload["error"] = "Ξ”ΞµΞ½ ΞΉΟƒΟ‡ΟΞµΞΉ Ο€Ξ»Ξ­ΞΏΞ½ ΟƒΟ…Ξ½ΞΈΞ®ΞΊΞ· ΞµΞΉΞ΄ΞΏΟ€ΞΏΞ―Ξ·ΟƒΞ·Ο‚ Ξ³ΞΉΞ± Ξ±Ο…Ο„Ξ® Ο„Ξ· Ξ³ΟΞ±ΞΌΞΌΞ®."
        return jsonify(payload), 400
    if not ok and not result["total"]:
        payload["error"] = (
            "Ξ”ΞµΞ½ Ο…Ο€Ξ¬ΟΟ‡ΞΏΟ…Ξ½ Ξ»Ξ®Ο€Ο„ΞµΟ‚ ΞΌΞµ ΟƒΟ…Ξ½Ξ΄ΞµΞ΄ΞµΞΌΞ­Ξ½ΞΏ Telegram. "
            "Ξ ΟΞΏΟƒΞΈΞ­ΟƒΟ„Ξµ Ξ»Ξ®Ο€Ο„ΞµΟ‚ ΟƒΟ„ΞΏ ΞΊΞ±Ο„Ξ¬ΟƒΟ„Ξ·ΞΌΞ± ΞΊΞ±ΞΉ /start ΟƒΟ„ΞΏ bot."
        )
    elif not ok:
        payload["error"] = "Ξ— Ξ±Ο€ΞΏΟƒΟ„ΞΏΞ»Ξ® Ξ±Ο€Ξ­Ο„Ο…Ο‡Ξµ Ξ³ΞΉΞ± ΟΞ»ΞΏΟ…Ο‚ Ο„ΞΏΟ…Ο‚ Ξ»Ξ®Ο€Ο„ΞµΟ‚"
    return jsonify(payload), (200 if ok else 400)


@telegram_bp.get("/today-hit/<token>")
def telegram_today_hit_preview(token: str):
    preview, err = today_hit_preview(token)
    if err:
        _audit_notification_open(
            "telegram.telegram_today_hit_preview",
            token=token,
            ok=False,
            error=err,
        )
        return jsonify({"error": err}), 400
    _audit_notification_open("telegram.telegram_today_hit_preview", token=token, ok=True)
    return jsonify({"ok": True, "preview": preview})


@telegram_bp.post("/today-hit/<token>/confirm")
def telegram_today_hit_confirm(token: str):
    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin") or "").strip()
    if not pin:
        return jsonify({"error": "Ξ›ΞµΞ―Ο€ΞµΞΉ PIN"}), 400
    if not is_valid_notify_pin(pin):
        return jsonify({"error": "Ξ PIN Ο€ΟΞ­Ο€ΞµΞΉ Ξ½Ξ± ΞµΞ―Ξ½Ξ±ΞΉ Ξ±ΞΊΟΞΉΞ²ΟΟ‚ 4 Ξ±ΟΞΉΞΈΞΌΞ·Ο„ΞΉΞΊΞ¬ ΟΞ·Ο†Ξ―Ξ±"}), 400
    result, status = confirm_today_hit_with_pin(token, pin)
    return jsonify(result), status


@telegram_bp.get("/today-action/context")
def telegram_today_action_context():
    from app.leave_types import LEAVE_TYPES

    token = str(request.args.get("t") or "").strip() or None
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        _audit_notification_open(
            "telegram.telegram_today_action_context",
            token=token,
            ok=False,
            error=err or "Ξ›Ξ®ΞΎΞ· ΟƒΟ…Ξ½ΞµΞ΄ΟΞ―Ξ±Ο‚",
        )
        return jsonify({"error": err or "Ξ›Ξ®ΞΎΞ· ΟƒΟ…Ξ½ΞµΞ΄ΟΞ―Ξ±Ο‚"}), 401
    _audit_notification_open("telegram.telegram_today_action_context", token=token, ok=True)
    payload = {"ok": True, "context": ctx}
    if ctx.get("leave_eligible"):
        payload["leave_types"] = LEAVE_TYPES
    return jsonify(payload)


@telegram_bp.post("/today-action/wto-daily")
def telegram_today_action_wto_daily():
    from app.today_alert_service import submit_today_wto_daily

    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip() or None
    result, status = submit_today_wto_daily(
        hour_from=data.get("hour_from"),
        hour_to=data.get("hour_to"),
        comments=data.get("comments"),
        token=token,
    )
    return jsonify(result), status


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
        return jsonify({"error": "Ξ›ΞµΞ―Ο€ΞµΞΉ leave_type"}), 400
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
        return jsonify({"error": "Ξ›ΞµΞ―Ο€ΞµΞΉ PIN"}), 400
    if not is_valid_notify_pin(pin):
        return jsonify({"error": "Ξ PIN Ο€ΟΞ­Ο€ΞµΞΉ Ξ½Ξ± ΞµΞ―Ξ½Ξ±ΞΉ Ξ±ΞΊΟΞΉΞ²ΟΟ‚ 4 Ξ±ΟΞΉΞΈΞΌΞ·Ο„ΞΉΞΊΞ¬ ΟΞ·Ο†Ξ―Ξ±"}), 400
    result, status = confirm_punch_with_pin(token, pin)
    return jsonify(result), status


@telegram_bp.get("/retro-hit/context")
def telegram_retro_hit_context():
    token = str(request.args.get("t") or "").strip() or None
    ctx, err = get_retro_hit_context(token=token)
    if err or not ctx:
        return jsonify({"error": err or "Ξ›Ξ®ΞΎΞ· ΟƒΟ…Ξ½ΞµΞ΄ΟΞ―Ξ±Ο‚"}), 401
    return jsonify({"ok": True, "context": ctx})


@telegram_bp.post("/retro-hit/submit")
def telegram_retro_hit_submit():
    data = request.get_json(silent=True) or {}
    event = str(data.get("event") or "").strip()
    reference_date = str(data.get("reference_date") or "").strip()
    retro_time = str(data.get("retro_time") or "").strip()
    aitiologia = str(data.get("aitiologia") or "").strip() or None
    token = str(data.get("token") or "").strip() or None
    result, status = submit_retro_hit_from_session(
        event=event,
        reference_date=reference_date,
        retro_time=retro_time,
        aitiologia=aitiologia,
        token=token,
    )
    return jsonify(result), status

