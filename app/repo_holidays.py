"""Repository για αργίες — γενικές + store overrides."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.db import cursor


def list_holidays(year: int | None = None) -> list[dict[str, Any]]:
    """Επιστρέφει όλες τις αργίες, προαιρετικά φιλτραρισμένες κατά έτος."""
    with cursor() as cur:
        if year:
            cur.execute(
                "SELECT id, holiday_date, name, recurring, recurring_month, recurring_day "
                "FROM dbo.karta_holidays WHERE YEAR(holiday_date)=? ORDER BY holiday_date",
                (year,),
            )
        else:
            cur.execute(
                "SELECT id, holiday_date, name, recurring, recurring_month, recurring_day "
                "FROM dbo.karta_holidays ORDER BY holiday_date"
            )
        return [
            {
                "id": r[0],
                "holiday_date": r[1].isoformat() if r[1] else None,
                "name": r[2],
                "recurring": bool(r[3]),
                "recurring_month": r[4],
                "recurring_day": r[5],
            }
            for r in cur.fetchall()
        ]


def add_holiday(holiday_date: date, name: str, *, recurring: bool = False) -> int:
    month = holiday_date.month if recurring else None
    day = holiday_date.day if recurring else None
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO dbo.karta_holidays (holiday_date, name, recurring, recurring_month, recurring_day) "
            "VALUES (?, ?, ?, ?, ?)",
            (holiday_date, name, recurring, month, day),
        )
        cur.execute("SELECT SCOPE_IDENTITY()")
        return int(cur.fetchone()[0])


def delete_holiday(holiday_id: int) -> bool:
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM dbo.karta_holidays WHERE id=?", (holiday_id,))
        return cur.rowcount > 0


def list_store_overrides(store_id: int) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(
            "SELECT id, holiday_date, action, custom_name "
            "FROM dbo.karta_store_holiday_overrides WHERE store_id=? ORDER BY holiday_date",
            (store_id,),
        )
        return [
            {"id": r[0], "holiday_date": r[1].isoformat() if r[1] else None, "action": r[2], "custom_name": r[3]}
            for r in cur.fetchall()
        ]


def set_store_override(store_id: int, holiday_date: date, action: str, custom_name: str | None = None) -> int:
    """action: 'add' (extra holiday) or 'remove' (not a holiday for this store)."""
    if action not in ("add", "remove"):
        raise ValueError("action must be 'add' or 'remove'")
    with cursor(commit=True) as cur:
        cur.execute("""
            MERGE dbo.karta_store_holiday_overrides AS t
            USING (SELECT ? AS store_id, ? AS holiday_date) AS s
            ON t.store_id = s.store_id AND t.holiday_date = s.holiday_date
            WHEN MATCHED THEN UPDATE SET action=?, custom_name=?
            WHEN NOT MATCHED THEN INSERT (store_id, holiday_date, action, custom_name) VALUES (?,?,?,?);
        """, (store_id, holiday_date, action, custom_name, store_id, holiday_date, action, custom_name))
        return cur.rowcount


def delete_store_override(store_id: int, holiday_date: date) -> bool:
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM dbo.karta_store_holiday_overrides WHERE store_id=? AND holiday_date=?",
            (store_id, holiday_date),
        )
        return cur.rowcount > 0


def get_effective_holidays_for_store(store_id: int, year: int) -> set[date]:
    """
    Επιστρέφει effective set αργιών για ένα κατάστημα και έτος.
    = (γενικές αργίες τού έτους) - (store removes) + (store adds).
    """
    with cursor() as cur:
        cur.execute(
            "SELECT holiday_date FROM dbo.karta_holidays WHERE YEAR(holiday_date)=?",
            (year,),
        )
        base = {r[0] for r in cur.fetchall()}

        cur.execute(
            "SELECT holiday_date, action FROM dbo.karta_store_holiday_overrides "
            "WHERE store_id=? AND YEAR(holiday_date)=?",
            (store_id, year),
        )
        for r in cur.fetchall():
            if r[1] == "remove":
                base.discard(r[0])
            elif r[1] == "add":
                base.add(r[0])

    return base


def is_holiday_or_sunday(store_id: int, check_date: date) -> bool:
    """True αν η ημέρα είναι Κυριακή ή αργία (γενική ή store-specific)."""
    if check_date.weekday() == 6:
        return True
    holidays = get_effective_holidays_for_store(store_id, check_date.year)
    return check_date in holidays
