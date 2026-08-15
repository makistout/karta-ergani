"""Persistence and authorization for Telegram assistant dry-run commands."""

from __future__ import annotations

import json
from typing import Any

from app.db import cursor
from app.row_util import rows_to_dicts


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
    proposed_action: str,
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
        cur.execute(
            """
            INSERT INTO dbo.karta_assistant_task
                (inbound_message_id, recipient_id, store_id, intent, task_status,
                 employee_afm, work_date, payload_json, llm_response_json, confidence,
                 validation_json, proposed_action_text, execution_enabled)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?, TRY_CONVERT(date, ?), ?, ?, ?, ?, ?, 0)
            """,
            (
                int(inbound_id), recipient_id, store_id,
                str(parsed.get("intent") or "unknown")[:64], status,
                str(parsed.get("employee_afm") or "")[:16] or None,
                str(parsed.get("date") or "")[:10] or None,
                _json(parsed), _json(parsed), confidence, _json(validation), proposed_action[:2000],
            ),
        )
        task_id = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO dbo.karta_assistant_task_event(task_id, event_type, event_json) VALUES (?, N'parsed_dry_run', ?)",
            (task_id, _json({"status": status, "validation": validation})),
        )
        return task_id
