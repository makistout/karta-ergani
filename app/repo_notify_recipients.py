"""Λήπτες ειδοποιήσεων Telegram ανά κατάστημα."""

from __future__ import annotations

import re
from typing import Any

import pyodbc

from app.db import cursor
from app.notify_pin import hash_notify_pin, is_pin_mask, pin_mask
from app.row_util import rows_to_dicts


def normalize_mobile(value: str | None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("30") and len(digits) > 10:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits[:32]


def notify_recipients_table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_store_notify_recipient" in str(exc):
            return (
                "Λείπει ο πίνακας karta_store_notify_recipient. "
                "Τρέξτε sql/alter_add_store_notify_recipients.sql στο SSMS."
            )
    return None


def mask_recipient_for_api(row: dict[str, Any]) -> dict[str, Any]:
    has_pin = bool((row.get("notify_pin_hash") or "").strip())
    out = {k: v for k, v in row.items() if k != "notify_pin_hash"}
    out["has_notify_pin"] = has_pin
    out["notify_pin"] = pin_mask() if has_pin else ""
    return out


def list_notify_recipients(store_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, store_id, name, mobile, telegram_chat_id, active, notify_pin_hash
            FROM dbo.karta_store_notify_recipient
            WHERE store_id = ?
            ORDER BY name, mobile, id
            """,
            (int(store_id),),
        )
        rows = rows_to_dicts(cur)
    return [mask_recipient_for_api(r) for r in rows]


def _list_notify_recipients_raw(store_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, store_id, name, mobile, telegram_chat_id, active, notify_pin_hash
            FROM dbo.karta_store_notify_recipient
            WHERE store_id = ?
            """,
            (int(store_id),),
        )
        return rows_to_dicts(cur)


def replace_notify_recipients(
    store_id: int,
    rows: list[dict[str, Any]],
) -> int:
    sid = int(store_id)
    old_pins = {
        normalize_mobile(r.get("mobile")): (r.get("notify_pin_hash") or "").strip() or None
        for r in _list_notify_recipients_raw(sid)
    }
    cleaned: list[tuple[str, str, str | None, str | None]] = []
    for row in rows:
        name = str(row.get("name") or "").strip()[:128]
        mobile = normalize_mobile(row.get("mobile"))
        if not name or not mobile:
            continue
        chat_id = str(row.get("telegram_chat_id") or "").strip()[:64] or None
        pin_raw = str(row.get("notify_pin") or "").strip()
        if is_pin_mask(pin_raw):
            pin_hash = old_pins.get(mobile)
        elif pin_raw:
            pin_hash = hash_notify_pin(store_id=sid, mobile=mobile, pin=pin_raw)
        else:
            pin_hash = None
        cleaned.append((name, mobile, chat_id, pin_hash))
    with cursor() as cur:
        cur.execute(
            "DELETE FROM dbo.karta_store_notify_recipient WHERE store_id = ?",
            (sid,),
        )
        for name, mobile, chat_id, pin_hash in cleaned:
            cur.execute(
                """
                INSERT INTO dbo.karta_store_notify_recipient (
                    store_id, name, mobile, telegram_chat_id, notify_pin_hash, active
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (sid, name, mobile, chat_id, pin_hash),
            )
        return len(cleaned)


def link_telegram_chat_by_mobile(mobile: str, chat_id: str) -> int:
    mob = normalize_mobile(mobile)
    cid = str(chat_id or "").strip()
    if not mob or not cid:
        return 0
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_store_notify_recipient
            SET telegram_chat_id = ?
            WHERE mobile = ? AND active = 1
            """,
            (cid, mob),
        )
        return int(cur.rowcount or 0)


def list_deliverable_recipients(store_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, name, mobile, telegram_chat_id, notify_pin_hash
            FROM dbo.karta_store_notify_recipient
            WHERE store_id = ? AND active = 1
              AND telegram_chat_id IS NOT NULL
              AND LTRIM(RTRIM(telegram_chat_id)) <> N''
            ORDER BY name, id
            """,
            (int(store_id),),
        )
        return rows_to_dicts(cur)
