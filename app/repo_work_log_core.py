"""Core SQL access for work-log rows."""

from __future__ import annotations

from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm


def _sql_employee_active_column(alias: str = "w") -> str:
    """1 αν ο εργαζόμενος έχει ενεργή απασχόληση στο ίδιο παράρτημα."""
    a = alias
    return f"""
        CAST(CASE WHEN EXISTS (
            SELECT 1 FROM dbo.karta_employment e
            INNER JOIN dbo.karta_employee emp ON emp.id = e.employee_id
            INNER JOIN dbo.karta_employer em ON em.id = e.employer_id
            LEFT JOIN dbo.karta_parartima p ON p.id = e.parartima_id
            WHERE emp.afm = {a}.employee_afm
              AND em.afm = {a}.employer_afm
              AND e.active = 1
              AND p.code_aa = {a}.branch_aa
        ) THEN 1 ELSE 0 END AS bit) AS employee_active
    """


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
            SELECT employee_afm, hour_from, hour_to, protocol_from, protocol_to
            FROM dbo.karta_work_log
            WHERE employer_afm = ? AND branch_aa = ? AND work_date = ?
            """,
            (afm, aa, wd),
        )
        preserved: dict[tuple[str | None, str, str], tuple[Any, Any]] = {}
        for emp, hf, ht, pf, pt in cur.fetchall():
            key = (
                norm_afm(emp) if emp else None,
                str(hf or "").strip(),
                str(ht or "").strip(),
            )
            preserved[key] = (pf, pt)

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
            hf = row.get("hour_from")
            ht = row.get("hour_to")
            key = (
                e_afm,
                str(hf or "").strip(),
                str(ht or "").strip(),
            )
            pf, pt = preserved.get(key, (None, None))
            cur.execute(
                """
                INSERT INTO dbo.karta_work_log (
                    employer_afm, branch_aa, work_date, employee_afm,
                    hour_from, hour_to, source_aa, is_end_date_different,
                    protocol_from, protocol_to
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    afm,
                    aa,
                    wd,
                    e_afm,
                    hf,
                    ht,
                    row.get("source_aa"),
                    row.get("is_end_date_different"),
                    pf,
                    pt,
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
                w.protocol_from, w.protocol_to,
                w.source_aa, w.is_end_date_different,
                emp.eponymo, emp.onoma, emp.flex_arrival_minutes,
                CAST(w.synced_at AS datetime2) AS synced_at,
                {_sql_employee_active_column("w")}
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            WHERE w.employer_afm = ? AND w.branch_aa = ? AND w.work_date = ?
            ORDER BY w.hour_from, emp.eponymo, w.employee_afm
            """,
            (afm, aa, wd),
        )
        return rows_to_dicts(cur)


def work_log_has_hour_from(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date: str,
) -> bool:
    """True αν υπάρχει γραμμή πραγματικής με μη κενό Από για εργαζόμενο/ημέρα."""
    erg = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    emp = norm_afm(employee_afm)
    wd = str(work_date or "").strip()
    if not erg or not emp or not wd:
        return False
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1) 1
            FROM dbo.karta_work_log
            WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
              AND (
                work_date = ?
                OR TRY_CONVERT(date, work_date, 103) = TRY_CONVERT(date, ?, 103)
              )
              AND NULLIF(LTRIM(RTRIM(ISNULL(hour_from, N''))), N'') IS NOT NULL
            """,
            (erg, aa, emp, wd, wd),
        )
        return cur.fetchone() is not None


def work_log_has_open_entry(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date: str,
) -> bool:
    """True αν υπάρχει πραγματική με Από και χωρίς Έως."""
    erg = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    emp = norm_afm(employee_afm)
    wd = str(work_date or "").strip()
    if not erg or not emp or not wd:
        return False
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1) 1
            FROM dbo.karta_work_log
            WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
              AND (
                work_date = ?
                OR TRY_CONVERT(date, work_date, 103) = TRY_CONVERT(date, ?, 103)
              )
              AND NULLIF(LTRIM(RTRIM(ISNULL(hour_from, N''))), N'') IS NOT NULL
              AND NULLIF(LTRIM(RTRIM(ISNULL(hour_to, N''))), N'') IS NULL
            """,
            (erg, aa, emp, wd, wd),
        )
        return cur.fetchone() is not None


def work_log_open_hour_from(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date: str,
) -> str | None:
    """Ώρα Από ανοιχτής πραγματικής (χωρίς Έως), αλλιώς None."""
    erg = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    emp = norm_afm(employee_afm)
    wd = str(work_date or "").strip()
    if not erg or not emp or not wd:
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1) hour_from
            FROM dbo.karta_work_log
            WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
              AND (
                work_date = ?
                OR TRY_CONVERT(date, work_date, 103) = TRY_CONVERT(date, ?, 103)
              )
              AND NULLIF(LTRIM(RTRIM(ISNULL(hour_from, N''))), N'') IS NOT NULL
              AND NULLIF(LTRIM(RTRIM(ISNULL(hour_to, N''))), N'') IS NULL
            ORDER BY id DESC
            """,
            (erg, aa, emp, wd, wd),
        )
        row = cur.fetchone()
    if not row:
        return None
    return str(row[0] or "").strip() or None


def work_log_closed_hour_to(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date: str,
) -> str | None:
    """Ώρα Έως κλειστής πραγματικής (Από+Έως), αλλιώς None."""
    erg = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    emp = norm_afm(employee_afm)
    wd = str(work_date or "").strip()
    if not erg or not emp or not wd:
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1) hour_to
            FROM dbo.karta_work_log
            WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
              AND (
                work_date = ?
                OR TRY_CONVERT(date, work_date, 103) = TRY_CONVERT(date, ?, 103)
              )
              AND NULLIF(LTRIM(RTRIM(ISNULL(hour_from, N''))), N'') IS NOT NULL
              AND NULLIF(LTRIM(RTRIM(ISNULL(hour_to, N''))), N'') IS NOT NULL
            ORDER BY id DESC
            """,
            (erg, aa, emp, wd, wd),
        )
        row = cur.fetchone()
    if not row:
        return None
    return str(row[0] or "").strip() or None


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
                w.protocol_from, w.protocol_to,
                w.source_aa, w.is_end_date_different,
                emp.eponymo, emp.onoma, emp.flex_arrival_minutes,
                CAST(w.synced_at AS datetime2) AS synced_at,
                {_sql_employee_active_column("w")}
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            WHERE w.employer_afm = ? AND w.branch_aa = ? AND w.work_date IN ({placeholders})
            ORDER BY w.work_date, w.hour_from, emp.eponymo
            """,
            (afm, aa, *dates),
        )
        return rows_to_dicts(cur)
