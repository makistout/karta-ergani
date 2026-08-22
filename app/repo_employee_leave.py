"""Read models for employee annual-leave usage."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.db import cursor


def load_current_year_normal_leave(
    *, store_id: int, employee_afms: list[str], today: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Bulk-load normal-leave days taken and entitlement for the current year."""
    as_of = today or date.today()
    afms = sorted({str(value or "").strip() for value in employee_afms if str(value or "").strip()})
    if not afms:
        return {}
    placeholders = ",".join("?" for _ in afms)
    sql = f"""
        SELECT employee_afm,
               MAX(leave_entitled_days) AS days_taken
        FROM dbo.karta_portal_schedule_archive
        WHERE store_id=? AND employee_afm IN ({placeholders})
          AND work_date>=? AND work_date<=?
          AND leave_reference_year=?
          AND LTRIM(RTRIM(leave_type)) = N'Κανονική άδεια'
        GROUP BY employee_afm
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, [int(store_id), *afms, date(as_of.year, 1, 1), as_of, as_of.year])
        records = cur.fetchall()
    return {
        str(record[0]).strip(): {
            "days_taken": int(record[1] or 0),
        }
        for record in records
    }


def load_schedule_archive_latest_month(*, store_id: int) -> date | None:
    """Return the latest archived reference month available for a store."""
    with cursor(commit=False) as cur:
        cur.execute(
            "SELECT MAX(reference_month) FROM dbo.karta_portal_schedule_archive WHERE store_id=?",
            int(store_id),
        )
        record = cur.fetchone()
    return record[0] if record and record[0] else None
