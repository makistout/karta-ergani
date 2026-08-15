"""Persistence and authorization for Telegram assistant dry-run commands."""

from __future__ import annotations

import json
from typing import Any

from app.db import cursor
from app.notify_pin import verify_notify_pin_for_recipient
from app.row_util import rows_to_dicts

_MAX_PIN_ATTEMPTS = 5


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def authorized_contexts(chat_id: str) -> list[dict[str, Any]]:
    """Only active recipients already linked to this Telegram chat are authorized."""
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT r.id AS recipient_id, r.name AS recipient_name, r.mobile,
                   r.store_id, s.name AS store_name, s.employer_afm, s.branch_aa
            FROM dbo.karta_store_notify_recipient r
            JOIN dbo.karta_store_config s ON s.id = r.store_id
            WHERE r.active = 1 AND LTRIM(RTRIM(ISNULL(r.telegram_chat_id, N''))) = ?
            ORDER BY s.name, r.id
            """,
            (str(chat_id).strip(),),
        )
        return rows_to_dicts(cur)


def create_inbound_message(
    *, update_id: int, message_id: int | None, reply_to_message_id: int | None,
    chat_id: str, recipient_id: int | None, store_id: int | None,
    text: str, raw_payload: dict[str, Any],
) -> tuple[int, bool]:
    """Insert once by Telegram update_id; return (id, created)."""
    with cursor() as cur:
        cur.execute(
            "SELECT id FROM dbo.karta_telegram_inbound_message WHERE telegram_update_id = ?",
            (int(update_id),),
        )
        existing = cur.fetchone()
        if existing:
            return int(existing[0]), False
        cur.execute(
            """
            INSERT INTO dbo.karta_telegram_inbound_message
                (telegram_update_id, telegram_message_id, reply_to_message_id, chat_id,
                 recipient_id, store_id, message_text, raw_payload_json)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(update_id), message_id, reply_to_message_id, str(chat_id)[:64],
                recipient_id, store_id, str(text)[:4096], _json(raw_payload),
            ),
        )
        return int(cur.fetchone()[0]), True


def mark_inbound(inbound_id: int, status: str, error: str | None = None) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_telegram_inbound_message
            SET processing_status=?, error_message=?, processed_at=SYSDATETIMEOFFSET()
            WHERE id=?
            """,
            (str(status)[:32], str(error)[:2000] if error else None, int(inbound_id)),
        )


def reply_context(chat_id: str, message_id: int | None) -> dict[str, Any] | None:
    if message_id is None:
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1) recipient_id, store_id, employee_afm, notification_type,
                   notification_reference_id, context_json
            FROM dbo.karta_telegram_outbound_message
            WHERE chat_id=? AND telegram_message_id=?
            """,
            (str(chat_id), int(message_id)),
        )
        rows = rows_to_dicts(cur)
    if not rows:
        return None
    row = rows[0]
    try:
        row["context"] = json.loads(row.get("context_json") or "{}")
    except (TypeError, ValueError):
        row["context"] = {}
    return row


def conversation_task(chat_id: str, reply_message_id: int | None = None) -> dict[str, Any] | None:
    """Resolve a pending task from a bot reply, or the latest pending chat task."""
    params: tuple[Any, ...]
    reply_filter = ""
    if reply_message_id is not None:
        reply_filter = """
            AND t.id = TRY_CONVERT(bigint, o.notification_reference_id)
            AND o.chat_id = i.chat_id
            AND o.telegram_message_id = ?
            AND o.notification_type IN (N'assistant_confirmation', N'assistant_pin')
        """
        params = (str(chat_id), int(reply_message_id))
    else:
        params = (str(chat_id),)
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP (1) t.id, t.recipient_id, t.store_id, t.task_status,
                   t.proposed_action_text, t.payload_json
            FROM dbo.karta_assistant_task t
            JOIN dbo.karta_telegram_inbound_message i ON i.id = t.inbound_message_id
            {'JOIN dbo.karta_telegram_outbound_message o ON 1=1' if reply_message_id is not None else ''}
            WHERE i.chat_id = ?
              AND t.task_status IN (N'awaiting_confirmation', N'awaiting_pin')
              {reply_filter}
            ORDER BY t.created_at DESC, t.id DESC
            """,
            params,
        )
        rows = rows_to_dicts(cur)
    if not rows:
        return None
    row = rows[0]
    try:
        row["payload"] = json.loads(row.get("payload_json") or "{}")
    except (TypeError, ValueError):
        row["payload"] = {}
    return row


def transition_task(
    task_id: int, *, expected_status: str, new_status: str, event_type: str,
) -> bool:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_assistant_task
            SET task_status=?, updated_at=SYSDATETIMEOFFSET()
            WHERE id=? AND task_status=? AND execution_enabled=0
            """,
            (new_status[:32], int(task_id), expected_status[:32]),
        )
        cur.execute("SELECT @@ROWCOUNT")
        changed = int(cur.fetchone()[0]) == 1
        if changed:
            cur.execute(
                "INSERT INTO dbo.karta_assistant_task_event(task_id, event_type, event_json) VALUES (?, ?, N'{}')",
                (int(task_id), event_type[:64]),
            )
        return changed


def verify_and_confirm_task_pin(task_id: int, *, chat_id: str, pin: str) -> tuple[str, dict[str, Any] | None]:
    """Verify the recipient PIN without persisting it; lock after repeated failures."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT TOP (1) t.id, t.task_status, t.store_id, t.proposed_action_text,
                   r.mobile, r.notify_pin_hash, r.notify_pin
            FROM dbo.karta_assistant_task t WITH (UPDLOCK, HOLDLOCK)
            JOIN dbo.karta_telegram_inbound_message i ON i.id=t.inbound_message_id
            JOIN dbo.karta_store_notify_recipient r ON r.id=t.recipient_id
            WHERE t.id=? AND i.chat_id=? AND r.active=1
              AND LTRIM(RTRIM(ISNULL(r.telegram_chat_id, N'')))=i.chat_id
              AND t.execution_enabled=0
            """,
            (int(task_id), str(chat_id)),
        )
        rows = rows_to_dicts(cur)
        if not rows:
            return "not_found", None
        task = rows[0]
        if task.get("task_status") != "awaiting_pin":
            return "invalid_state", task
        if not str(task.get("notify_pin_hash") or "").strip() and not str(task.get("notify_pin") or "").strip():
            return "not_configured", task
        cur.execute(
            "SELECT COUNT(*) FROM dbo.karta_assistant_task_event WHERE task_id=? AND event_type=N'pin_failed'",
            (int(task_id),),
        )
        attempts = int(cur.fetchone()[0])
        if attempts >= _MAX_PIN_ATTEMPTS:
            cur.execute(
                "UPDATE dbo.karta_assistant_task SET task_status=N'pin_locked', updated_at=SYSDATETIMEOFFSET() WHERE id=?",
                (int(task_id),),
            )
            return "locked", task
        valid = verify_notify_pin_for_recipient(
            store_id=int(task["store_id"]),
            mobile=task.get("mobile"),
            pin=pin,
            pin_hash=task.get("notify_pin_hash"),
            pin_plain=task.get("notify_pin"),
        )
        if not valid:
            attempts += 1
            cur.execute(
                "INSERT INTO dbo.karta_assistant_task_event(task_id, event_type, event_json) VALUES (?, N'pin_failed', ?)",
                (int(task_id), _json({"attempt": attempts})),
            )
            if attempts >= _MAX_PIN_ATTEMPTS:
                cur.execute(
                    "UPDATE dbo.karta_assistant_task SET task_status=N'pin_locked', updated_at=SYSDATETIMEOFFSET() WHERE id=?",
                    (int(task_id),),
                )
                return "locked", task
            return "invalid", task
        cur.execute(
            """
            UPDATE dbo.karta_assistant_task
            SET task_status=N'confirmed_dry_run', confirmed_at=SYSDATETIMEOFFSET(),
                updated_at=SYSDATETIMEOFFSET()
            WHERE id=? AND task_status=N'awaiting_pin' AND execution_enabled=0
            """,
            (int(task_id),),
        )
        cur.execute(
            "INSERT INTO dbo.karta_assistant_task_event(task_id, event_type, event_json) VALUES (?, N'pin_verified_dry_run', N'{}')",
            (int(task_id),),
        )
        return "confirmed", task


def record_outbound_message(
    *, chat_id: str, telegram_message_id: int, text: str,
    context: dict[str, Any] | None = None,
) -> None:
    ctx = context or {}
    with cursor() as cur:
        cur.execute(
            """
            IF NOT EXISTS (
                SELECT 1 FROM dbo.karta_telegram_outbound_message
                WHERE chat_id=? AND telegram_message_id=?
            )
            INSERT INTO dbo.karta_telegram_outbound_message
                (telegram_message_id, chat_id, recipient_id, store_id, employee_afm,
                 notification_type, notification_reference_id, message_text, context_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(chat_id), int(telegram_message_id), int(telegram_message_id), str(chat_id)[:64],
                ctx.get("recipient_id"), ctx.get("store_id"), str(ctx.get("employee_afm") or "")[:16] or None,
                str(ctx.get("notification_type") or "")[:64] or None,
                str(ctx.get("notification_reference_id") or "")[:128] or None,
                str(text)[:4096], _json(ctx),
            ),
        )


def create_task(
    *, inbound_id: int, recipient_id: int | None, store_id: int | None,
    parsed: dict[str, Any], status: str, validation: dict[str, Any],
    proposed_action: str, llm_metadata: dict[str, Any] | None = None,
) -> int:
    with cursor() as cur:
        cur.execute(
            "SELECT id FROM dbo.karta_assistant_task WHERE inbound_message_id=?",
            (int(inbound_id),),
        )
        existing = cur.fetchone()
        if existing:
            return int(existing[0])
        confidence = parsed.get("confidence")
        try:
            confidence = max(0.0, min(float(confidence), 1.0))
        except (TypeError, ValueError):
            confidence = None
        employee_afms = parsed.get("employee_afms")
        if not isinstance(employee_afms, list):
            employee_afms = [parsed.get("employee_afm")] if parsed.get("employee_afm") else []
        employee_afms = [str(value or "").strip() for value in employee_afms if str(value or "").strip()]
        employee_afm = employee_afms[0] if len(employee_afms) == 1 else None
        metadata = llm_metadata or {}
        usage = metadata.get("usage_metadata")
        if not isinstance(usage, dict):
            usage = {}

        def _usage_int(name: str) -> int | None:
            try:
                return max(0, int(usage[name])) if usage.get(name) is not None else None
            except (TypeError, ValueError):
                return None

        cur.execute(
            """
            INSERT INTO dbo.karta_assistant_task
                (inbound_message_id, recipient_id, store_id, intent, task_status,
                 employee_afm, work_date, payload_json, llm_response_json, confidence,
                 validation_json, proposed_action_text, execution_enabled,
                 gemini_model, prompt_token_count, candidates_token_count,
                 total_token_count, cached_content_token_count, thoughts_token_count,
                 tool_use_prompt_token_count, llm_duration_ms, usage_metadata_json)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, TRY_CONVERT(date, ?), ?, ?, ?, ?, ?, 0,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(inbound_id), recipient_id, store_id,
                str(parsed.get("intent") or "unknown")[:64], status,
                employee_afm[:16] if employee_afm else None,
                str(parsed.get("date") or "")[:10] or None,
                _json(parsed), _json(parsed), confidence, _json(validation), proposed_action[:2000],
                str(metadata.get("model") or "")[:128] or None,
                _usage_int("promptTokenCount"), _usage_int("candidatesTokenCount"),
                _usage_int("totalTokenCount"), _usage_int("cachedContentTokenCount"),
                _usage_int("thoughtsTokenCount"), _usage_int("toolUsePromptTokenCount"),
                max(0, int(metadata.get("duration_ms") or 0)), _json(usage),
            ),
        )
        task_id = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO dbo.karta_assistant_task_event(task_id, event_type, event_json) VALUES (?, N'parsed_dry_run', ?)",
            (task_id, _json({"status": status, "validation": validation, "llm": metadata})),
        )
        return task_id
