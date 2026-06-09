"""Πραγματική απασχόληση (EX_BASE_07) — pyodbc."""

from __future__ import annotations

from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm


def work_log_table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_work_log" in str(exc):
            return (
                "Λείπει ο πίνακας karta_work_log στη βάση. "
                "Τρέξτε το sql/alter_add_karta_work_log.sql στο SSMS."
            )
    return None


def replace_work_log_for_day(
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
            DELETE FROM dbo.karta_work_log
            WHERE employer_afm = ? AND branch_aa = ? AND work_date = ?
            """,
            (afm, aa, wd),
        )
        n = 0
        for row in rows:
            e_afm = norm_afm(row.get("employee_afm") or "") if row.get("employee_afm") else None
            cur.execute(
                """
                INSERT INTO dbo.karta_work_log (
                    employer_afm, branch_aa, work_date, employee_afm,
                    hour_from, hour_to, source_aa, is_end_date_different
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    afm,
                    aa,
                    wd,
                    e_afm,
                    row.get("hour_from"),
                    row.get("hour_to"),
                    row.get("source_aa"),
                    row.get("is_end_date_different"),
                ),
            )
            n += 1
        return n


def list_work_log_for_store(
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
                w.id, w.employee_afm, w.hour_from, w.hour_to, w.work_date,
                w.source_aa, w.is_end_date_different,
                emp.eponymo, emp.onoma, emp.flex_arrival_minutes,
                CAST(w.synced_at AS datetime2) AS synced_at
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            WHERE w.employer_afm = ? AND w.branch_aa = ? AND w.work_date = ?
            ORDER BY w.hour_from, emp.eponymo, w.employee_afm
            """,
            (afm, aa, wd),
        )
        return rows_to_dicts(cur)


def list_work_log_for_range(
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
                w.id, w.employee_afm, w.hour_from, w.hour_to, w.work_date,
                w.source_aa, w.is_end_date_different,
                emp.eponymo, emp.onoma, emp.flex_arrival_minutes,
                CAST(w.synced_at AS datetime2) AS synced_at
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            WHERE w.employer_afm = ? AND w.branch_aa = ? AND w.work_date IN ({placeholders})
            ORDER BY w.work_date, w.hour_from, emp.eponymo
            """,
            (afm, aa, *dates),
        )
        return rows_to_dicts(cur)
