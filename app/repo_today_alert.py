"""Tokens και snooze για ειδοποιήσεις τύπου 2 (τρέχουσα ημέρα)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm, tz_athens

_MAX_PIN_ATTEMPTS = 5
_TOKEN_TTL_HOURS = 24


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_snoozed(
    *,
    store_id: int,
    employee_afm: str,
    work_date_ergani: str,
    notify_kind: str,
) -> bool:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT 1
            FROM dbo.karta_today_notify_snooze
            WHERE store_id = ? AND employee_afm = ? AND work_date_ergani = ?
              AND notify_kind = ?
            """,
            (
                int(store_id),
                norm_afm(employee_afm),
                work_date_ergani.strip()[:32],
                notify_kind.strip()[:32],
            ),
        )
        return cur.fetchone() is not None


def list_today_notify_snoozes(
    store_id: int,
    work_dates_ergani: list[str],
) -> set[tuple[str, str, str]]:
    """Σύνολο (afm, work_date_ergani, notify_kind) σε αναβολή για το κατάστημα."""
    dates = [d.strip()[:32] for d in work_dates_ergani if (d or "").strip()]
    if not dates:
        return set()
    placeholders = ",".join("?" * len(dates))
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT employee_afm, work_date_ergani, notify_kind
            FROM dbo.karta_today_notify_snooze
            WHERE store_id = ? AND work_date_ergani IN ({placeholders})
            """,
            (int(store_id), *dates),
        )
        rows = rows_to_dicts(cur)
    return {
        (
            norm_afm(str(r.get("employee_afm") or "")),
            str(r.get("work_date_ergani") or "").strip(),
            str(r.get("notify_kind") or "").strip(),
        )
        for r in rows
    }


def enrich_work_log_rows_with_today_notify_snooze(
    rows: list[dict[str, Any]],
    store_id: int,
    ergani_dates: list[str],
) -> None:
    """Σημαία today_notify_snoozed αν η τρέχουσα περίπτωση είναι σε αναβολή."""
    from app.today_notify_logic import resolve_today_notify_kind

    snoozed = list_today_notify_snoozes(store_id, ergani_dates)
    for row in rows:
        kind = resolve_today_notify_kind(row)
        if not kind:
            row["today_notify_snoozed"] = False
            continue
        key = (
            norm_afm(str(row.get("employee_afm") or "")),
            str(row.get("work_date") or "").strip(),
            kind,
        )
        row["today_notify_snoozed"] = key in snoozed


def create_snooze(
    *,
    store_id: int,
    recipient_id: int | None,
    employee_afm: str,
    work_date_ergani: str,
    notify_kind: str,
    acted_by_name: str | None = None,
    acted_by_mobile: str | None = None,
    acted_via: str | None = None,
    office_user: str | None = None,
    client_ip: str | None = None,
    client_device: str | None = None,
) -> None:
    with cursor() as cur:
        cur.execute(
            """
            IF NOT EXISTS (
                SELECT 1 FROM dbo.karta_today_notify_snooze
                WHERE store_id = ? AND employee_afm = ? AND work_date_ergani = ?
                  AND notify_kind = ?
            )
            BEGIN
                INSERT INTO dbo.karta_today_notify_snooze (
                    store_id, recipient_id, employee_afm, work_date_ergani, notify_kind,
                    acted_by_name, acted_by_mobile, acted_via, office_user,
                    client_ip, client_device
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            END
            """,
            (
                int(store_id),
                norm_afm(employee_afm),
                work_date_ergani.strip()[:32],
                notify_kind.strip()[:32],
                int(store_id),
                int(recipient_id) if recipient_id else None,
                norm_afm(employee_afm),
                work_date_ergani.strip()[:32],
                notify_kind.strip()[:32],
                (acted_by_name or "").strip()[:200] or None,
                (acted_by_mobile or "").strip()[:32] or None,
                (acted_via or "").strip()[:32] or None,
                (office_user or "").strip()[:128] or None,
                (client_ip or "").strip()[:45] or None,
                (client_device or "").strip()[:2000] or None,
            ),
        )


def create_today_alert_token(
    *,
    recipient_id: int,
    store_id: int,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date_ergani: str,
    reference_date_iso: str,
    notify_kind: str,
    hour_from: str | None,
    hour_to: str | None,
    schedule_hour_from: str | None,
) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = datetime.now(tz_athens())
    expires = now + timedelta(hours=_TOKEN_TTL_HOURS)
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_telegram_today_alert_token (
                token_hash, recipient_id, store_id, employee_afm,
                eponymo, onoma, work_date_ergani, reference_date_iso,
                notify_kind, hour_from, hour_to, schedule_hour_from, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                token_hash,
                int(recipient_id),
                int(store_id),
                norm_afm(employee_afm),
                (eponymo or "").strip()[:200] or None,
                (onoma or "").strip()[:200] or None,
                work_date_ergani.strip()[:32],
                reference_date_iso.strip()[:10],
                notify_kind.strip()[:32],
                (hour_from or "").strip()[:8] or None,
                (hour_to or "").strip()[:8] or None,
                (schedule_hour_from or "").strip()[:8] or None,
                expires,
            ),
        )
    return token


def get_today_alert_token_row(token: str) -> dict[str, Any] | None:
    th = _hash_token(token.strip())
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
                t.id, t.token_hash, t.recipient_id, t.store_id, t.employee_afm,
                t.eponymo, t.onoma, t.work_date_ergani, t.reference_date_iso,
                t.notify_kind, t.hour_from, t.hour_to, t.schedule_hour_from,
                t.pin_attempts, t.action_taken,
                CAST(t.pin_verified_at AS datetime2) AS pin_verified_at,
                CAST(t.created_at AS datetime2) AS created_at,
                CAST(t.expires_at AS datetime2) AS expires_at,
                CAST(t.used_at AS datetime2) AS used_at,
                r.mobile, r.notify_pin_hash, r.name AS recipient_name,
                s.name AS store_name, s.employer_afm, s.branch_aa
            FROM dbo.karta_telegram_today_alert_token t
            INNER JOIN dbo.karta_store_notify_recipient r ON r.id = t.recipient_id
            INNER JOIN dbo.karta_store_config s ON s.id = t.store_id
            WHERE t.token_hash = ?
            """,
            (th,),
        )
        rows = rows_to_dicts(cur)
    return rows[0] if rows else None


def get_today_alert_token_row_by_id(token_id: int) -> dict[str, Any] | None:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT
                t.id, t.token_hash, t.recipient_id, t.store_id, t.employee_afm,
                t.eponymo, t.onoma, t.work_date_ergani, t.reference_date_iso,
                t.notify_kind, t.hour_from, t.hour_to, t.schedule_hour_from,
                t.pin_attempts, t.action_taken,
                CAST(t.pin_verified_at AS datetime2) AS pin_verified_at,
                CAST(t.created_at AS datetime2) AS created_at,
                CAST(t.expires_at AS datetime2) AS expires_at,
                CAST(t.used_at AS datetime2) AS used_at,
                r.mobile, r.notify_pin_hash, r.name AS recipient_name,
                s.name AS store_name, s.employer_afm, s.branch_aa
            FROM dbo.karta_telegram_today_alert_token t
            INNER JOIN dbo.karta_store_notify_recipient r ON r.id = t.recipient_id
            INNER JOIN dbo.karta_store_config s ON s.id = t.store_id
            WHERE t.id = ?
            """,
            (int(token_id),),
        )
        rows = rows_to_dicts(cur)
    return rows[0] if rows else None


def increment_today_alert_pin_attempts(token_id: int) -> int:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_telegram_today_alert_token
            SET pin_attempts = pin_attempts + 1
            OUTPUT INSERTED.pin_attempts
            WHERE id = ?
            """,
            (int(token_id),),
        )
        row = cur.fetchone()
        return int(row[0] if row else 0)


def mark_today_alert_pin_verified(token_id: int) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_telegram_today_alert_token
            SET pin_verified_at = SYSDATETIMEOFFSET()
            WHERE id = ? AND pin_verified_at IS NULL
            """,
            (int(token_id),),
        )


def mark_today_alert_action(token_id: int, action: str) -> None:
    act = (action or "").strip()[:32]
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_telegram_today_alert_token
            SET action_taken = ?, used_at = SYSDATETIMEOFFSET()
            WHERE id = ? AND used_at IS NULL
            """,
            (act, int(token_id)),
        )


def today_alert_token_is_valid(row: dict[str, Any] | None) -> tuple[bool, str | None]:
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
