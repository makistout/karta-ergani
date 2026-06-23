"""Λήπτες ειδοποιήσεων ανά κατάστημα."""

from __future__ import annotations

import re
from typing import Any

import pyodbc

from app.db import cursor
from app.notify_pin import hash_notify_pin, is_pin_mask, validate_notify_pin
from app.row_util import rows_to_dicts


def normalize_mobile(value: str | None) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("30") and len(digits) > 10:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits[:32]


def normalize_email(value: str | None) -> str:
    email = str(value or "").strip().lower()
    if not email or "@" not in email:
        return ""
    return email[:254]


def notify_recipients_table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_store_notify_recipient" in str(exc):
            return (
                "Λείπει ο πίνακας karta_store_notify_recipient. "
                "Τρέξτε sql/alter_add_store_notify_recipients.sql στο SSMS."
            )
        if err == "42S22" or "email_active" in str(exc) or "Invalid column name" in str(exc):
            return (
                "Λείπουν πεδία email στους λήπτες ειδοποιήσεων. "
                "Τρέξτε sql/alter_add_notify_recipient_email.sql."
            )
    return None


def recipient_for_api(row: dict[str, Any]) -> dict[str, Any]:
    has_hash = bool((row.get("notify_pin_hash") or "").strip())
    plain = str(row.get("notify_pin") or "").strip()
    out = {k: v for k, v in row.items() if k != "notify_pin_hash"}
    out["has_notify_pin"] = has_hash or bool(plain)
    out["notify_pin"] = plain
    out["active"] = bool(row.get("active")) if row.get("active") is not None else True
    out["email_active"] = (
        bool(row.get("email_active")) if row.get("email_active") is not None else True
    )
    return out


def list_notify_recipients(store_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, store_id, name, mobile, telegram_chat_id, active,
                   email, email_active,
                   notify_pin_hash, notify_pin
            FROM dbo.karta_store_notify_recipient
            WHERE store_id = ?
            ORDER BY name, mobile, id
            """,
            (int(store_id),),
        )
        rows = rows_to_dicts(cur)
    return [recipient_for_api(r) for r in rows]


def _list_notify_recipients_raw(store_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, store_id, name, mobile, telegram_chat_id, active,
                   email, email_active,
                   notify_pin_hash, notify_pin
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
    old_rows = {
        normalize_mobile(r.get("mobile")): r for r in _list_notify_recipients_raw(sid)
    }
    cleaned: list[
        tuple[str, str, str | None, str | None, int, str | None, str | None, int]
    ] = []
    for row in rows:
        name = str(row.get("name") or "").strip()[:128]
        mobile = normalize_mobile(row.get("mobile"))
        if not name or not mobile:
            continue
        chat_id = str(row.get("telegram_chat_id") or "").strip()[:64] or None
        email = normalize_email(row.get("email")) or None
        pin_raw = str(row.get("notify_pin") or "").strip()
        prev = old_rows.get(mobile) or {}
        if is_pin_mask(pin_raw):
            pin_hash = (prev.get("notify_pin_hash") or "").strip() or None
            pin_plain = str(prev.get("notify_pin") or "").strip() or None
        elif pin_raw:
            pin_plain = validate_notify_pin(pin_raw)
            pin_hash = hash_notify_pin(store_id=sid, mobile=mobile, pin=pin_plain)
        elif (prev.get("notify_pin_hash") or "").strip():
            pin_hash = (prev.get("notify_pin_hash") or "").strip() or None
            pin_plain = str(prev.get("notify_pin") or "").strip() or None
        else:
            pin_hash = None
            pin_plain = None
        active_raw = row.get("active")
        if active_raw is None:
            active = 1 if bool(prev.get("active", True)) else 0
        elif active_raw in (False, 0, "0", "false", "False"):
            active = 0
        else:
            active = 1
        email_active_raw = row.get("email_active")
        if email_active_raw is None:
            email_active = 1 if bool(prev.get("email_active", True)) else 0
        elif email_active_raw in (False, 0, "0", "false", "False"):
            email_active = 0
        else:
            email_active = 1
        cleaned.append(
            (name, mobile, chat_id, email, email_active, pin_hash, pin_plain, active)
        )
    with cursor() as cur:
        cur.execute(
            "DELETE FROM dbo.karta_store_notify_recipient WHERE store_id = ?",
            (sid,),
        )
        for name, mobile, chat_id, email, email_active, pin_hash, pin_plain, active in cleaned:
            cur.execute(
                """
                INSERT INTO dbo.karta_store_notify_recipient (
                    store_id, name, mobile, telegram_chat_id, email, email_active,
                    notify_pin_hash, notify_pin, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    name,
                    mobile,
                    chat_id,
                    email,
                    email_active,
                    pin_hash,
                    pin_plain,
                    active,
                ),
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


def list_email_deliverable_recipients(store_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, name, mobile, email, notify_pin_hash
            FROM dbo.karta_store_notify_recipient
            WHERE store_id = ? AND email_active = 1
              AND email IS NOT NULL
              AND LTRIM(RTRIM(email)) <> N''
            ORDER BY name, id
            """,
            (int(store_id),),
        )
        return rows_to_dicts(cur)
