"""Εργοδότες / εργαζόμενοι — pyodbc."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm


def list_employees(limit: int = 500) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 2000))
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP ({lim}) id, afm, eponymo, onoma, created_at, updated_at
            FROM dbo.karta_employee
            ORDER BY eponymo, onoma, afm
            """
        )
        return rows_to_dicts(cur)


def list_active_employees_for_store(
    employer_afm: str,
    branch_aa: str,
    *,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Ενεργοί εργαζόμενοι ενός καταστήματος (employer AFM + branch AA)."""
    return list_employees_for_employer(
        employer_afm,
        branch_aa=branch_aa,
        active_only=True,
        limit=limit,
    )


def list_employees_for_employer(
    employer_afm: str,
    branch_aa: str | None = None,
    active_only: bool = True,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 5000))
    afm = norm_afm(employer_afm)
    sql = f"""
        SELECT TOP ({lim})
            emp.id, emp.afm, emp.eponymo, emp.onoma, emp.flex_arrival_minutes,
            e.active, e.hire_date, e.departure_date, p.code_aa AS parartima_aa,
            p.description AS parartima_desc,
            em.afm AS employer_afm,
            em.eponimia AS employer_eponimia,
            CAST(emp.updated_at AS datetime2) AS updated_at
        FROM dbo.karta_employee emp
        JOIN dbo.karta_employment e ON emp.id = e.employee_id
        JOIN dbo.karta_employer em ON e.employer_id = em.id
        LEFT JOIN dbo.karta_parartima p ON e.parartima_id = p.id
        WHERE em.afm = ?
    """
    params: list[Any] = [afm]
    if active_only:
        sql += " AND e.active = 1"
    if branch_aa is not None:
        sql += " AND p.code_aa = ?"
        params.append(str(branch_aa).strip()[:32])
    sql += " ORDER BY emp.eponymo, emp.onoma, emp.afm"
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        return rows_to_dicts(cur)


def update_employment_dates(
    employer_afm: str, branch_aa: str, employee_afm: str,
    *, hire_date: date | None, departure_date: date | None,
) -> None:
    """Persist the editable active interval on the store employment card."""
    with cursor() as cur:
        cur.execute(
            """
            UPDATE e SET hire_date=?, departure_date=?,
                active=CASE WHEN ? IS NULL OR ? >= CAST(GETDATE() AS date) THEN 1 ELSE 0 END,
                updated_at=SYSDATETIMEOFFSET()
            FROM dbo.karta_employment e
            JOIN dbo.karta_employee emp ON emp.id=e.employee_id
            JOIN dbo.karta_employer em ON em.id=e.employer_id
            LEFT JOIN dbo.karta_parartima p ON p.id=e.parartima_id
            WHERE em.afm=? AND emp.afm=? AND p.code_aa=?
            """,
            (hire_date, departure_date, departure_date, departure_date,
             norm_afm(employer_afm), norm_afm(employee_afm), str(branch_aa or "0")),
        )
        if not cur.rowcount:
            raise ValueError("Δεν βρέθηκε η εργασιακή σύνδεση του εργαζομένου στο κατάστημα")


def upsert_employer(
    cur: pyodbc.Cursor,
    afm: str,
    eponimia: str | None = None,
) -> int | None:
    a = norm_afm(afm)
    cur.execute("SELECT id FROM dbo.karta_employer WHERE afm = ?", (a,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE dbo.karta_employer
            SET eponimia = COALESCE(?, eponimia),
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            (eponimia, int(row[0])),
        )
        return int(row[0])
    cur.execute(
        """
        INSERT INTO dbo.karta_employer (afm, eponimia)
        OUTPUT INSERTED.id VALUES (?, ?)
        """,
        (a, eponimia),
    )
    ins = cur.fetchone()
    return int(ins[0]) if ins else None


def upsert_parartima(
    cur: pyodbc.Cursor,
    employer_id: int,
    aa: str,
    description: str | None = None,
) -> int | None:
    code = str(aa or "0").strip()[:32] or "0"
    cur.execute(
        "SELECT id FROM dbo.karta_parartima WHERE employer_id = ? AND code_aa = ?",
        (employer_id, code),
    )
    row = cur.fetchone()
    if row:
        if description:
            cur.execute(
                """
                UPDATE dbo.karta_parartima
                SET description = ?, updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                (description[:500], int(row[0])),
            )
        return int(row[0])
    cur.execute(
        """
        INSERT INTO dbo.karta_parartima (employer_id, code_aa, description)
        OUTPUT INSERTED.id VALUES (?, ?, ?)
        """,
        (employer_id, code, (description or "")[:500] or None),
    )
    ins = cur.fetchone()
    return int(ins[0]) if ins else None


def deactivate_stale_employments(
    cur: pyodbc.Cursor,
    employer_id: int,
    active_afms: set[str],
    *,
    parartima_id: int | None = None,
) -> int:
    sql = """
        SELECT e.id, emp.afm
        FROM dbo.karta_employment e
        JOIN dbo.karta_employee emp ON e.employee_id = emp.id
        WHERE e.employer_id = ? AND e.active = 1
    """
    params: list[Any] = [employer_id]
    if parartima_id is not None:
        sql += " AND e.parartima_id = ?"
        params.append(int(parartima_id))
    cur.execute(sql, params)
    n = 0
    for row in cur.fetchall():
        emp_afm = norm_afm(str(row[1]))
        if emp_afm not in active_afms:
            cur.execute(
                """
                UPDATE dbo.karta_employment
                SET active = 0, updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                (int(row[0]),),
            )
            n += 1
    return n


def upsert_employee_by_afm(
    afm: str,
    eponymo: str | None,
    onoma: str | None,
    *,
    flex_arrival_minutes: int | None = None,
) -> int | None:
    """Δημιουργία/ενημέρωση εργαζόμενου από ΑΦΜ (π.χ. μετά από portal ωράριο)."""
    ep = (eponymo or "").strip()[:200] or None
    on = (onoma or "").strip()[:200] or None
    if not norm_afm(afm):
        return None
    if not ep and not on and flex_arrival_minutes is None:
        return None
    with cursor() as cur:
        return upsert_employee(
            cur, afm, ep, on, flex_arrival_minutes=flex_arrival_minutes
        )


def list_unlinked_activity_employees(
    employer_afm: str, branch_aa: str
) -> list[dict[str, Any]]:
    """Εργαζόμενοι με ωράριο/χτύπημα αλλά χωρίς σύνδεση στο συγκεκριμένο σημείο."""
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    with cursor(commit=False) as cur:
        cur.execute(
            """
            WITH activity AS (
                SELECT employee_afm, COUNT_BIG(*) AS schedule_count, CAST(0 AS bigint) AS work_log_count
                FROM dbo.karta_schedule
                WHERE employer_afm=? AND branch_aa=? AND employee_afm IS NOT NULL
                GROUP BY employee_afm
                UNION ALL
                SELECT employee_afm, CAST(0 AS bigint), COUNT_BIG(*)
                FROM dbo.karta_work_log
                WHERE employer_afm=? AND branch_aa=? AND employee_afm IS NOT NULL
                GROUP BY employee_afm
            ), totals AS (
                SELECT employee_afm, SUM(schedule_count) schedule_count, SUM(work_log_count) work_log_count
                FROM activity GROUP BY employee_afm
            )
            SELECT emp.afm, emp.eponymo, emp.onoma, totals.schedule_count, totals.work_log_count
            FROM totals
            INNER JOIN dbo.karta_employee emp ON emp.afm=totals.employee_afm
            WHERE NOT EXISTS (
                SELECT 1
                FROM dbo.karta_employment e
                INNER JOIN dbo.karta_employer em ON em.id=e.employer_id
                LEFT JOIN dbo.karta_parartima p ON p.id=e.parartima_id
                WHERE e.employee_id=emp.id AND em.afm=? AND p.code_aa=?
            )
            ORDER BY emp.eponymo, emp.onoma, emp.afm
            """,
            (afm, aa, afm, aa, afm, aa),
        )
        return rows_to_dicts(cur)


def link_employee_to_store(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    *,
    flex_arrival_minutes: int | None = None,
) -> bool:
    """Δημιουργεί/ενεργοποιεί σύνδεση μόνο για επιβεβαιωμένο εργαζόμενο Μητρώου."""
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    with cursor() as cur:
        employer_id = upsert_employer(cur, afm)
        if not employer_id:
            return False
        part_id = upsert_parartima(cur, employer_id, aa)
        employee_id = upsert_employee(
            cur, employee_afm, eponymo, onoma,
            flex_arrival_minutes=flex_arrival_minutes,
        )
        if not employee_id:
            return False
        upsert_employment(cur, employer_id, employee_id, part_id)
        return True


def flex_arrival_map_for_employer(
    employer_afm: str,
    branch_aa: str | None = None,
) -> dict[str, int | None]:
    """ΑΦΜ εργαζόμενου → ευέλικτη προσέλευση (λεπτά) — προαιρετικά ανά παράρτημα."""
    afm = norm_afm(employer_afm)
    sql = """
            SELECT emp.afm, emp.flex_arrival_minutes
            FROM dbo.karta_employee emp
            JOIN dbo.karta_employment e ON emp.id = e.employee_id
            JOIN dbo.karta_employer em ON e.employer_id = em.id
            LEFT JOIN dbo.karta_parartima p ON p.id = e.parartima_id
            WHERE em.afm = ? AND e.active = 1
    """
    params: list[Any] = [afm]
    if branch_aa is not None:
        sql += " AND p.code_aa = ?"
        params.append(str(branch_aa).strip()[:32])
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        out: dict[str, int | None] = {}
        for row in cur.fetchall():
            emp_afm = str(row[0]).strip()
            flex = row[1]
            out[emp_afm] = int(flex) if flex is not None else None
        return out


def upsert_employee(
    cur: pyodbc.Cursor,
    afm: str,
    eponymo: str | None,
    onoma: str | None,
    *,
    flex_arrival_minutes: int | None = None,
) -> int | None:
    a = norm_afm(afm)
    cur.execute("SELECT id FROM dbo.karta_employee WHERE afm = ?", (a,))
    row = cur.fetchone()
    if row:
        if flex_arrival_minutes is not None:
            cur.execute(
                """
                UPDATE dbo.karta_employee
                SET eponymo = COALESCE(NULLIF(?, ''), eponymo),
                    onoma = COALESCE(NULLIF(?, ''), onoma),
                    flex_arrival_minutes = ?,
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                (eponymo or "", onoma or "", int(flex_arrival_minutes), int(row[0])),
            )
        else:
            cur.execute(
                """
                UPDATE dbo.karta_employee
                SET eponymo = COALESCE(NULLIF(?, ''), eponymo),
                    onoma = COALESCE(NULLIF(?, ''), onoma),
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                (eponymo or "", onoma or "", int(row[0])),
            )
        return int(row[0])
    cur.execute(
        """
        INSERT INTO dbo.karta_employee (afm, eponymo, onoma, flex_arrival_minutes)
        OUTPUT INSERTED.id VALUES (?, ?, ?, ?)
        """,
        (a, eponymo, onoma, flex_arrival_minutes),
    )
    ins = cur.fetchone()
    return int(ins[0]) if ins else None


def upsert_employment(
    cur: pyodbc.Cursor,
    employer_id: int,
    employee_id: int,
    parartima_id: int | None,
) -> None:
    cur.execute(
        """
        SELECT id FROM dbo.karta_employment
        WHERE employer_id = ? AND employee_id = ?
          AND (
            (parartima_id = ? AND ? IS NOT NULL)
            OR (parartima_id IS NULL AND ? IS NULL)
          )
        """,
        (employer_id, employee_id, parartima_id, parartima_id, parartima_id),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE dbo.karta_employment
            SET parartima_id = ?, active = 1, updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            (parartima_id, int(row[0])),
        )
        return
    cur.execute(
        """
        INSERT INTO dbo.karta_employment (employer_id, employee_id, parartima_id, active)
        VALUES (?, ?, ?, 1)
        """,
        (employer_id, employee_id, parartima_id),
    )


def find_employee_for_employer(
    cur: pyodbc.Cursor, employee_afm: str, employer_afm: str
) -> tuple[str | None, str | None, bool | None]:
    cur.execute(
        """
        SELECT emp.eponymo, emp.onoma, e.active
        FROM dbo.karta_employee emp
        JOIN dbo.karta_employment e ON emp.id = e.employee_id
        JOIN dbo.karta_employer em ON e.employer_id = em.id
        WHERE emp.afm = ? AND em.afm = ?
        """,
        (employee_afm, employer_afm),
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1], bool(row[2])
    cur.execute(
        "SELECT eponymo, onoma FROM dbo.karta_employee WHERE afm = ?",
        (employee_afm,),
    )
    row2 = cur.fetchone()
    if row2:
        return row2[0], row2[1], None
    return None, None, None
