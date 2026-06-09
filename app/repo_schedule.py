"""Ψηφιακό ωράριο (EX_BASE_08) — pyodbc."""

from __future__ import annotations

from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm


def schedule_table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_schedule" in str(exc):
            return (
                "Λείπει ο πίνακας karta_schedule στη βάση. "
                "Τρέξτε το sql/alter_add_karta_schedule.sql στο SSMS."
            )
    return None


def replace_schedule_for_day(
    employer_afm: str,
    branch_aa: str,
    work_date: str,
    rows: list[dict[str, Any]],
) -> int:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    wd = str(work_date).strip()
    with cursor() as cur:
        cur.execute(
            """
            DELETE FROM dbo.karta_schedule
            WHERE employer_afm = ? AND branch_aa = ? AND work_date = ?
            """,
            (afm, aa, wd),
        )
        n = 0
        for row in rows:
            e_afm = norm_afm(row.get("employee_afm") or "") if row.get("employee_afm") else None
            cur.execute(
                """
                INSERT INTO dbo.karta_schedule (
                    employer_afm, branch_aa, work_date, employee_afm,
                    hour_from, hour_to, shift_type, break_minutes, break_in_work,
                    extra, source_aa
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    afm,
                    aa,
                    wd,
                    e_afm,
                    row.get("hour_from"),
                    row.get("hour_to"),
                    row.get("shift_type"),
                    int(row.get("break_minutes") or 0),
                    int(row.get("break_in_work") or 0),
                    row.get("extra"),
                    row.get("source_aa"),
                ),
            )
            n += 1
        return n


def _has_schedule_hours(row: dict[str, Any]) -> bool:
    hf = (row.get("hour_from") or "").strip()
    ht = (row.get("hour_to") or "").strip()
    return bool(hf or ht)


def _ergani_date_sort_key(work_date: str | None) -> tuple[int, int, int]:
    parts = (work_date or "").strip().split("/")
    if len(parts) == 3:
        try:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            return (y, m, d)
        except ValueError:
            pass
    return (9999, 12, 31)


def _schedule_sort_key(row: dict[str, Any]) -> tuple:
    wd = _ergani_date_sort_key(row.get("work_date"))
    if _has_schedule_hours(row):
        return (
            wd,
            0,
            (row.get("hour_from") or "").strip() or "99:99",
            (row.get("eponymo") or "").upper(),
            row.get("employee_afm") or "",
        )
    shift = (row.get("shift_type") or "").strip().upper()
    return (
        wd,
        1,
        0 if shift else 1,
        shift,
        (row.get("eponymo") or "").upper(),
        row.get("employee_afm") or "",
    )


def sort_schedule_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ανά ημερομηνία· μέσα στην ημέρα πρώτα με ώρες, μετά χωρίς (αλφαβητικά τύπος)."""
    return sorted(rows, key=_schedule_sort_key)


def list_schedule_for_store(
    employer_afm: str,
    branch_aa: str,
    work_date: str,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 10000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    wd = str(work_date).strip()
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP ({lim})
                s.id, s.employee_afm, s.hour_from, s.hour_to, s.shift_type,
                s.break_minutes, s.break_in_work, s.extra, s.work_date,
                emp.eponymo, emp.onoma,
                CAST(s.synced_at AS datetime2) AS synced_at
            FROM dbo.karta_schedule s
            LEFT JOIN dbo.karta_employee emp ON emp.afm = s.employee_afm
            WHERE s.employer_afm = ? AND s.branch_aa = ? AND s.work_date = ?
            ORDER BY s.hour_from, emp.eponymo, s.employee_afm
            """,
            (afm, aa, wd),
        )
        return rows_to_dicts(cur)


def list_schedule_for_range(
    employer_afm: str,
    branch_aa: str,
    work_dates: list[str],
    limit: int = 10000,
) -> list[dict[str, Any]]:
    if not work_dates:
        return []
    lim = max(1, min(int(limit), 20000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    dates = list(dict.fromkeys(str(d).strip() for d in work_dates if d))[:62]
    placeholders = ",".join("?" for _ in dates)
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP ({lim})
                s.id, s.employee_afm, s.hour_from, s.hour_to, s.shift_type,
                s.break_minutes, s.break_in_work, s.extra, s.work_date,
                emp.eponymo, emp.onoma,
                CAST(s.synced_at AS datetime2) AS synced_at
            FROM dbo.karta_schedule s
            LEFT JOIN dbo.karta_employee emp ON emp.afm = s.employee_afm
            WHERE s.employer_afm = ? AND s.branch_aa = ? AND s.work_date IN ({placeholders})
            ORDER BY s.work_date, s.hour_from, emp.eponymo
            """,
            (afm, aa, *dates),
        )
        return rows_to_dicts(cur)
