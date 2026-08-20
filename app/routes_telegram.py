"""Telegram Bot β€” webhook ΟƒΟΞ½Ξ΄ΞµΟƒΞ·Ο‚ Ξ»Ξ·Ο€Ο„ΟΞ½ + Ξ΄ΞΏΞΊΞΉΞΌΞ±ΟƒΟ„ΞΉΞΊΞ® Ξ±Ο€ΞΏΟƒΟ„ΞΏΞ»Ξ®."""

from __future__ import annotations

import logging
import copy

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


from app.assistant_messages import ai_agent_disabled_message as _ai_agent_disabled_message


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


def _reply_chat(
    chat_id: str, text: str, *, context: dict | None = None,
    reply_markup: dict | None = None,
) -> None:
    """Ξ‘Ο€Ξ¬Ξ½Ο„Ξ·ΟƒΞ· ΟƒΟ„ΞΏΞ½ Ο‡ΟΞ®ΟƒΟ„Ξ· β€” Ο€Ξ¬Ξ½Ο„Ξ± Ξ±ΞΈΟΟΟ…Ξ²Ξ± ΟƒΞµ ΟƒΟ†Ξ¬Ξ»ΞΌΞ± (Ο„ΞΏ webhook Ο€ΟΞ­Ο€ΞµΞΉ Ξ½Ξ± ΞµΟ€ΞΉΟƒΟ„ΟΞ­Ο†ΞµΞΉ 200)."""
    try:
        send_telegram_message(str(chat_id), text, context=context, reply_markup=reply_markup)
    except TelegramNotConfigured:
        logger.warning("Telegram webhook: bot token not configured")
    except Exception:
        logger.exception("Telegram webhook: failed to reply chat_id=%s", chat_id)


@telegram_bp.post("/webhook")
def telegram_webhook():
    """Ξ Ξ»Ξ®Ο€Ο„Ξ·Ο‚ ΟƒΟ„Ξ­Ξ»Ξ½ΞµΞΉ: /start 6912345678 β†’ ΟƒΟΞ½Ξ΄ΞµΟƒΞ· chat_id ΞΌΞµ ΞΊΞΉΞ½Ξ·Ο„Ο ΟƒΟ„Ξ· Ξ²Ξ¬ΟƒΞ·."""
    update = request.get_json(silent=True) or {}
    callback = update.get("callback_query") or {}
    if callback:
        return _handle_assistant_callback(callback)
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = str(message.get("text") or "").strip()
    if not chat_id or not text:
        return jsonify({"ok": True})

    if not text.startswith("/start"):
        return _handle_assistant_message(update, message, str(chat_id), text)

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


def _handle_assistant_callback(callback: dict):
    data = str(callback.get("data") or "")
    message = callback.get("message") or {}
    chat_id = str(((message.get("chat") or {}).get("id") or "")).strip()
    if not chat_id or not data.startswith("assistant_confirm:"):
        return jsonify({"ok": True})
    try:
        task_id = int(data.split(":", 1)[1])
    except (TypeError, ValueError):
        return jsonify({"ok": True})
    from app.repo_telegram_assistant import authorized_contexts, conversation_task
    if not authorized_contexts(chat_id):
        return jsonify({"ok": True})
    task = conversation_task(chat_id)
    if not task or int(task.get("id") or 0) != task_id:
        _reply_chat(chat_id, "Η εντολή δεν είναι πλέον διαθέσιμη για επιβεβαίωση.")
        return jsonify({"ok": True, "assistant": "confirmation_unavailable"})
    _reply_chat(chat_id, "Στείλτε τον προσωπικό 4ψήφιο PIN σας.")
    return jsonify({"ok": True, "assistant": "awaiting_pin"})


def _handle_assistant_message(update: dict, message: dict, chat_id: str, text: str):
    """Store and parse authorized commands. Phase 1 never executes them."""
    from app.repo_telegram_assistant import (
        authorized_contexts,
        conversation_task,
        create_inbound_message,
        create_task,
        latest_chat_context,
        mark_inbound,
        reply_context,
        verify_and_confirm_task_pin,
    )

    contexts = authorized_contexts(chat_id)
    if not contexts:
        # Deliberately silent: unknown Telegram users are neither stored nor answered.
        return jsonify({"ok": True})

    # Only stores with an active subscription may reach parsing, PIN handling,
    # task creation, or any other AI-assisted Telegram response.
    enabled_contexts = [
        row for row in contexts
        if bool(int(row.get("ai_agent_enabled", 1) or 0))
    ]
    if not enabled_contexts:
        _reply_chat(chat_id, _ai_agent_disabled_message())
        return jsonify({"ok": True, "assistant": "store_disabled"})
    contexts = enabled_contexts

    update_id = update.get("update_id")
    message_id = message.get("message_id")
    reply_message = message.get("reply_to_message") or {}
    reply_message_id = reply_message.get("message_id")
    if update_id is None:
        return jsonify({"ok": True})

    one_store = {int(row["store_id"]) for row in contexts}
    recipient_id = int(contexts[0]["recipient_id"]) if len(contexts) == 1 else None
    store_id = next(iter(one_store)) if len(one_store) == 1 else None
    conversation = None
    if is_valid_notify_pin(text):
        conversation = conversation_task(
            chat_id, int(reply_message_id) if reply_message_id is not None else None,
        )

    stored_text = text
    stored_update = update
    if conversation:
        stored_text = "[REDACTED_PIN]"
        stored_update = copy.deepcopy(update)
        if isinstance(stored_update.get("message"), dict):
            stored_update["message"]["text"] = "[REDACTED_PIN]"

    inbound_id, created = create_inbound_message(
        update_id=int(update_id),
        message_id=int(message_id) if message_id is not None else None,
        reply_to_message_id=int(reply_message_id) if reply_message_id is not None else None,
        chat_id=chat_id,
        recipient_id=recipient_id,
        store_id=store_id,
        text=stored_text,
        raw_payload=stored_update,
    )
    if not created:
        return jsonify({"ok": True, "duplicate": True})
    if not Config.TELEGRAM_ASSISTANT_ENABLED:
        mark_inbound(inbound_id, "disabled")
        return jsonify({"ok": True, "assistant": "disabled"})

    if conversation:
        task_id = int(conversation["id"])
        try:
            pin_result, task = verify_and_confirm_task_pin(task_id, chat_id=chat_id, pin=text)
        except Exception:
            logger.exception("Telegram assistant PIN verification failed task_id=%s", task_id)
            mark_inbound(inbound_id, "failed", "PIN verification failed")
            _reply_chat(chat_id, "Δεν μπόρεσα να επαληθεύσω τον PIN. Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ.")
            return jsonify({"ok": True, "assistant": "pin_verification_failed"})
        mark_inbound(inbound_id, "conversation")
        if pin_result == "confirmed":
            from app.assistant_execution_service import execute_confirmed_task, execution_answer
            _reply_chat(chat_id, "Εκτέλεση εντολών. Παρακαλώ περιμένετε...")
            result = execute_confirmed_task(task or conversation, source="assistant_telegram")
            _reply_chat(chat_id, execution_answer(task_id, result))
            record_audit_event(
                action="assistant.execute", success=bool(result.get("success")),
                entity_type="assistant_task", entity_id=str(task_id),
                details={"channel": "telegram", "store_id": conversation.get("store_id"), "result": result},
            )
            return jsonify({"ok": True, "assistant": "completed" if result.get("success") else "failed"})
        if pin_result == "locked":
            _reply_chat(chat_id, f"Η εντολή #{task_id} κλειδώθηκε λόγω πολλών λανθασμένων προσπαθειών PIN.")
            return jsonify({"ok": True, "assistant": "pin_locked"})
        if pin_result == "not_configured":
            _reply_chat(chat_id, "Δεν έχει οριστεί προσωπικός PIN για αυτόν τον λήπτη. Η εντολή δεν επιβεβαιώθηκε.")
            return jsonify({"ok": True, "assistant": "pin_not_configured"})
        _reply_chat(chat_id, "Λάθος PIN. Δοκιμάστε ξανά ή στείλτε ξανά την εντολή.")
        return jsonify({"ok": True, "assistant": "awaiting_pin"})

    try:
        reply_ctx = reply_context(chat_id, int(reply_message_id)) if reply_message_id is not None else None
        if reply_ctx:
            reply_ctx["focus_locked"] = True
        else:
            reply_ctx = latest_chat_context(chat_id)
        reply_ctx = dict(reply_ctx or {})
        replied_text = str(reply_message.get("text") or reply_message.get("caption") or "").strip()
        if replied_text:
            reply_ctx.setdefault("message_text", replied_text[:4096])
        from app.assistant_conversation_service import process_assistant_command
        result = process_assistant_command(
            text=text, contexts=contexts, inbound_id=inbound_id,
            recipient_id=recipient_id, store_id=store_id,
            reply_context=reply_ctx, confirmation_mode="pin",
            chat_id=str(chat_id),
        )
        task_id = result["task_id"]
        status = result["status"]
        answer = result["answer"]
        parsed = result["parsed"]
        selected_recipient = result["recipient_id"]
        reply_markup = (
            {"inline_keyboard": [[{"text": "Επιβεβαίωση με PIN", "callback_data": f"assistant_confirm:{task_id}"}]]}
            if status == "draft" else None
        )
        notification_type = (
            "assistant_pin" if status == "draft"
            else "assistant_reply" if status == "answered"
            else "assistant_clarification"
        )
        _reply_chat(chat_id, answer, context={
            "notification_type": notification_type,
            "notification_reference_id": str(task_id),
            "recipient_id": selected_recipient,
            "store_id": parsed.get("store_id"),
            "employee_afm": parsed.get("employee_afm"),
            "employee_afms": parsed.get("employee_afms") or [],
        }, reply_markup=reply_markup)
        record_audit_event(
            action="assistant.message", success=True, entity_type="assistant_task",
            entity_id=str(task_id), details={"channel": "telegram", "store_id": parsed.get("store_id")},
        )
    except Exception as ex:
        logger.exception("Telegram assistant parsing failed")
        mark_inbound(inbound_id, "failed", str(ex))
        _reply_chat(chat_id, "Δεν μπόρεσα να αναλύσω την εντολή. Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ.")
    return jsonify({"ok": True})


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
    correction_mode = bool(data.get("correction_mode"))
    result, status = submit_retro_hit_from_session(
        event=event,
        reference_date=reference_date,
        retro_time=retro_time,
        aitiologia=aitiologia,
        token=token,
        correction_mode=correction_mode,
    )
    return jsonify(result), status
