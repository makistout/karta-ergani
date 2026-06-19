"""Tokens προσωρινής σύνδεσης για αυτόματο χτύπημα κάρτας από Telegram."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm, tz_athens

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
            SELECT
                t.id, t.token_hash, t.recipient_id, t.store_id, t.employee_afm,
                t.eponymo, t.onoma, t.work_date_ergani, t.reference_date_iso,
                t.card_event, t.retro_time, t.pin_attempts,
                CAST(t.pin_verified_at AS datetime2) AS pin_verified_at,
                CAST(t.created_at AS datetime2) AS created_at,
                CAST(t.expires_at AS datetime2) AS expires_at,
                CAST(t.used_at AS datetime2) AS used_at,
                r.mobile, r.notify_pin_hash, r.name AS recipient_name,
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


def get_punch_token_row_by_id(token_id: int) -> dict[str, Any] | None:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
                t.id, t.token_hash, t.recipient_id, t.store_id, t.employee_afm,
                t.eponymo, t.onoma, t.work_date_ergani, t.reference_date_iso,
                t.card_event, t.retro_time, t.pin_attempts,
                CAST(t.pin_verified_at AS datetime2) AS pin_verified_at,
                CAST(t.created_at AS datetime2) AS created_at,
                CAST(t.expires_at AS datetime2) AS expires_at,
                CAST(t.used_at AS datetime2) AS used_at,
                r.mobile, r.notify_pin_hash, r.name AS recipient_name,
                s.name AS store_name, s.employer_afm, s.branch_aa
            FROM dbo.karta_telegram_punch_token t
            INNER JOIN dbo.karta_store_notify_recipient r ON r.id = t.recipient_id
            INNER JOIN dbo.karta_store_config s ON s.id = t.store_id
            WHERE t.id = ?
            """,
            (int(token_id),),
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


def mark_pin_verified(token_id: int) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_telegram_punch_token
            SET pin_verified_at = SYSDATETIMEOFFSET()
            WHERE id = ? AND pin_verified_at IS NULL
            """,
            (int(token_id),),
        )


def mark_token_used(token_id: int, *, retro_time: str | None = None) -> None:
    rt = (retro_time or "").strip()[:8] or None
    with cursor() as cur:
        if rt:
            cur.execute(
                """
                UPDATE dbo.karta_telegram_punch_token
                SET used_at = SYSDATETIMEOFFSET(), retro_time = ?
                WHERE id = ? AND used_at IS NULL
                """,
                (rt, int(token_id)),
            )
        else:
            cur.execute(
                """
                UPDATE dbo.karta_telegram_punch_token
                SET used_at = SYSDATETIMEOFFSET()
                WHERE id = ? AND used_at IS NULL
                """,
                (int(token_id),),
            )


def _card_event_to_f_type(card_event: str) -> str | None:
    ev = (card_event or "").strip().lower()
    if ev in ("check_in", "0"):
        return "0"
    if ev in ("check_out", "1"):
        return "1"
    return None


def list_completed_punch_tokens_by_employee_date(
    store_id: int,
    work_dates: list[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Ολοκληρωμένα retro-hit (used_at) ανά εργαζόμενο/ημέρα."""
    dates = [str(d or "").strip() for d in work_dates if str(d or "").strip()]
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    sql = f"""
        SELECT
            t.employee_afm, t.work_date_ergani, t.card_event, t.retro_time,
            CAST(t.used_at AS datetime2) AS used_at
        FROM dbo.karta_telegram_punch_token t
        WHERE t.store_id = ? AND t.used_at IS NOT NULL
          AND t.work_date_ergani IN ({placeholders})
    """
    params: list[Any] = [int(store_id), *dates]
    out: dict[tuple[str, str], dict[str, Any]] = {}
    from app.repo_work_log import _format_recorded_at

    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        for row in rows_to_dicts(cur):
            afm = norm_afm(row.get("employee_afm") or "")
            wd = str(row.get("work_date_ergani") or "").strip()
            ft = _card_event_to_f_type(str(row.get("card_event") or ""))
            if not afm or not wd or not ft:
                continue
            slot = out.setdefault(
                (afm, wd),
                {"types": set(), "check_in": None, "check_out": None},
            )
            rt = str(row.get("retro_time") or "").strip()
            entry = {
                "time": rt or None,
                "protocol": None,
                "from_token": True,
                "recorded_at": _format_recorded_at(row.get("used_at")),
            }
            if ft == "1":
                prev = slot.get("check_out")
                if not prev or (rt and not prev.get("time")):
                    slot["check_out"] = entry
            else:
                prev = slot.get("check_in")
                if not prev or (rt and not prev.get("time")):
                    slot["check_in"] = entry
    return out


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
