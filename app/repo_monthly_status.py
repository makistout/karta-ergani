"""Μηνιαία κατάσταση απασχόλησης (EX_BASE_04) — pyodbc."""

from __future__ import annotations

from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm


def monthly_status_table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_monthly_status" in str(exc):
            return (
                "Λείπει ο πίνακας karta_monthly_status στη βάση. "
                "Τρέξτε το sql/alter_add_karta_monthly_status.sql στο SSMS."
            )
    return None


def _int_val(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        try:
            return int(float(str(value).strip()))
        except ValueError:
            return None


def replace_monthly_status_for_period(
    employer_afm: str,
    branch_aa: str,
    report_year: int,
    report_month: int,
    rows: list[dict[str, Any]],
) -> int:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    year = int(report_year)
    month = int(report_month)
    with cursor() as cur:
        cur.execute(
            """
            DELETE FROM dbo.karta_monthly_status
            WHERE employer_afm = ? AND branch_aa = ? AND report_year = ? AND report_month = ?
            """,
            (afm, aa, year, month),
        )
        n = 0
        for row in rows:
            e_afm = norm_afm(row.get("employee_afm") or "")
            if not e_afm:
                continue
            cur.execute(
                """
                INSERT INTO dbo.karta_monthly_status (
                    employer_afm, branch_aa, ergodoti_id,
                    report_year, report_month, employee_afm,
                    days_work, days_telework, days_repo, days_no_work,
                    days_normal_leave, overtime_minutes, overtime_days,
                    days_work_card, days_leave_insurance, days_sick_insurance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    afm,
                    aa,
                    row.get("ergodoti_id"),
                    year,
                    month,
                    e_afm,
                    _int_val(row.get("days_work")),
                    _int_val(row.get("days_telework")),
                    _int_val(row.get("days_repo")),
                    _int_val(row.get("days_no_work")),
                    _int_val(row.get("days_normal_leave")),
                    _int_val(row.get("overtime_minutes")),
                    _int_val(row.get("overtime_days")),
                    _int_val(row.get("days_work_card")),
                    _int_val(row.get("days_leave_insurance")),
                    _int_val(row.get("days_sick_insurance")),
                ),
            )
            n += 1
        return n


def list_monthly_status(
    employer_afm: str,
    branch_aa: str,
    *,
    report_year: int | None = None,
    report_month: int | None = None,
    employee_afm: str | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 10000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    sql = f"""
        SELECT TOP ({lim})
            ms.report_year,
            ms.report_month,
            ms.employee_afm,
            ms.ergodoti_id,
            ms.branch_aa,
            ms.days_work,
            ms.days_telework,
            ms.days_repo,
            ms.days_no_work,
            ms.days_normal_leave,
            ms.overtime_minutes,
            ms.overtime_days,
            ms.days_work_card,
            ms.days_leave_insurance,
            ms.days_sick_insurance,
            ms.synced_at,
            emp.eponymo,
            emp.onoma
        FROM dbo.karta_monthly_status ms
        LEFT JOIN dbo.karta_employee emp ON emp.afm = ms.employee_afm
        WHERE ms.employer_afm = ? AND ms.branch_aa = ?
    """
    params: list[Any] = [afm, aa]
    if report_year is not None:
        sql += " AND ms.report_year = ?"
        params.append(int(report_year))
    if report_month is not None:
        sql += " AND ms.report_month = ?"
        params.append(int(report_month))
    if employee_afm:
        sql += " AND ms.employee_afm = ?"
        params.append(norm_afm(employee_afm))
    sql += " ORDER BY ms.report_year DESC, ms.report_month DESC, emp.eponymo, emp.onoma, ms.employee_afm"
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        return rows_to_dicts(cur)
