"""Read models needed by the timekeeping engine."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.db import cursor


def _duration_minutes(hour_from: Any, hour_to: Any) -> int:
    try:
        start = datetime.strptime(str(hour_from or "").strip(), "%H:%M")
        end = datetime.strptime(str(hour_to or "").strip(), "%H:%M")
    except (TypeError, ValueError):
        return 0
    minutes = int((end - start).total_seconds() // 60)
    return minutes + (1440 if minutes < 0 else 0)


def load_annual_overtime_context(
    *, store_id: int, employee_afms: list[str], period_from: date,
) -> dict[str, dict[str, Any]]:
    """Bulk-load prior YTD overtime; never queries once per employee."""
    afms = sorted({str(value or "").strip() for value in employee_afms if str(value or "").strip()})
    if not afms:
        return {}
    placeholders = ",".join("?" for _ in afms)
    year_from = date(period_from.year, 1, 1)
    sql = f"""
        SELECT employee_afm, work_date, overtime_from, overtime_to, synced_at
        FROM dbo.karta_portal_schedule_archive
        WHERE store_id=? AND employee_afm IN ({placeholders})
          AND work_date>=? AND work_date<?
          AND overtime_from IS NOT NULL AND overtime_to IS NOT NULL
        ORDER BY employee_afm, work_date
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, [int(store_id), *afms, year_from, period_from])
        records = cur.fetchall()

    result = {
        afm: {
            "legal_overtime_minutes_before_period": 0,
            "annual_limit_minutes": 150 * 60,
            "coverage_from": year_from.isoformat(),
            "coverage_to": (period_from - timedelta(days=1)).isoformat(),
            "data_complete": True,
            "last_synced_at": None,
        }
        for afm in afms
    }
    for record in records:
        afm = str(record[0])
        bucket = result.setdefault(afm, {})
        bucket["legal_overtime_minutes_before_period"] = int(
            bucket.get("legal_overtime_minutes_before_period") or 0
        ) + _duration_minutes(record[2], record[3])
        if record[4]:
            synced = record[4].isoformat()
            bucket["last_synced_at"] = max(str(bucket.get("last_synced_at") or ""), synced) or synced
    return result

