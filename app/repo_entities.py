"""Εργοδότες / εργαζόμενοι — pyodbc."""

from __future__ import annotations

import json
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
            emp.id, emp.afm, emp.eponymo, emp.onoma,
            e.active, p.code_aa AS parartima_aa,
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
        sql += " AND (p.code_aa = ? OR p.code_aa IS NULL)"
        params.append(str(branch_aa).strip()[:32])
    sql += " ORDER BY emp.eponymo, emp.onoma, emp.afm"
    with cursor(commit=False) as cur:
        cur.execute(sql, params)
        return rows_to_dicts(cur)


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
) -> int:
    cur.execute(
        """
        SELECT e.id, emp.afm
        FROM dbo.karta_employment e
        JOIN dbo.karta_employee emp ON e.employee_id = emp.id
        WHERE e.employer_id = ? AND e.active = 1
        """,
        (employer_id,),
    )
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
) -> int | None:
    """Δημιουργία/ενημέρωση εργαζόμενου από ΑΦΜ (π.χ. μετά από portal ωράριο)."""
    ep = (eponymo or "").strip()[:200] or None
    on = (onoma or "").strip()[:200] or None
    if not norm_afm(afm):
        return None
    if not ep and not on:
        return None
    with cursor() as cur:
        return upsert_employee(cur, afm, ep, on)


def upsert_employee(
    cur: pyodbc.Cursor,
    afm: str,
    eponymo: str | None,
    onoma: str | None,
) -> int | None:
    a = norm_afm(afm)
    cur.execute("SELECT id FROM dbo.karta_employee WHERE afm = ?", (a,))
    row = cur.fetchone()
    if row:
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
        INSERT INTO dbo.karta_employee (afm, eponymo, onoma)
        OUTPUT INSERTED.id VALUES (?, ?, ?)
        """,
        (a, eponymo, onoma),
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
        """,
        (employer_id, employee_id),
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
