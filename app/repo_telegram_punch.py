"""Tokens προσωρινής σύνδεσης για αυτόματο χτύπημα κάρτας από Telegram."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import tz_athens

_MAX_PIN_ATTEMPTS = 5
_TOKEN_TTL_HOURS = 72


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_punch_token(
    *,
    recipient_id: int,
    store_id: int,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date_ergani: str,
    reference_date_iso: str,
    card_event: str,
    retro_time: str,
) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = datetime.now(tz_athens())
    expires = now + timedelta(hours=_TOKEN_TTL_HOURS)
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_telegram_punch_token (
                token_hash, recipient_id, store_id, employee_afm,
                eponymo, onoma, work_date_ergani, reference_date_iso,
                card_event, retro_time, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_hash,
                int(recipient_id),
                int(store_id),
                employee_afm.strip()[:9],
                (eponymo or "").strip()[:200] or None,
                (onoma or "").strip()[:200] or None,
                work_date_ergani.strip()[:32],
                reference_date_iso.strip()[:10],
                card_event.strip()[:16],
                retro_time.strip()[:8],
                expires,
            ),
        )
    return token


def get_punch_token_row(token: str) -> dict[str, Any] | None:
    th = _hash_token(token.strip())
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT t.*, r.mobile, r.notify_pin_hash, r.name AS recipient_name,
                   s.name AS store_name, s.employer_afm, s.branch_aa
            FROM dbo.karta_telegram_punch_token t
            INNER JOIN dbo.karta_store_notify_recipient r ON r.id = t.recipient_id
            INNER JOIN dbo.karta_store_config s ON s.id = t.store_id
            WHERE t.token_hash = ?
            """,
            (th,),
        )
        rows = rows_to_dicts(cur)
    return rows[0] if rows else None


def increment_pin_attempts(token_id: int) -> int:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_telegram_punch_token
            SET pin_attempts = pin_attempts + 1
            OUTPUT INSERTED.pin_attempts
            WHERE id = ?
            """,
            (int(token_id),),
        )
        row = cur.fetchone()
        return int(row[0] if row else 0)


def mark_token_used(token_id: int) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_telegram_punch_token
            SET used_at = SYSDATETIMEOFFSET()
            WHERE id = ? AND used_at IS NULL
            """,
            (int(token_id),),
        )


def token_is_valid(row: dict[str, Any] | None) -> tuple[bool, str | None]:
    if not row:
        return False, "Μη έγκυρος ή ληγμένος σύνδεσμος"
    if row.get("used_at"):
        return False, "Ο σύνδεσμος έχει ήδη χρησιμοποιηθεί"
    attempts = int(row.get("pin_attempts") or 0)
    if attempts >= _MAX_PIN_ATTEMPTS:
        return False, "Υπερβολικά πολλές αποτυχημένες προσπάθειες PIN"
    exp = row.get("expires_at")
    if exp is not None:
        now = datetime.now(tz_athens())
        if hasattr(exp, "tzinfo") and exp.tzinfo is None:
            exp = exp.replace(tzinfo=tz_athens())
        if exp < now:
            return False, "Ο σύνδεσμος έληξε"
    if not (row.get("notify_pin_hash") or "").strip():
        return False, "Δεν έχει οριστεί PIN για αυτόν τον λήπτη"
    return True, None
