"""Εργοδότες / εργαζόμενοι — pyodbc."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm

_employee_amka_cols: bool | None = None


def employee_amka_columns_available() -> bool:
    global _employee_amka_cols
    if _employee_amka_cols is True:
        return _employee_amka_cols
    try:
        with cursor(commit=False) as cur:
            cur.execute("SELECT COL_LENGTH(N'dbo.karta_employee', N'amka')")
            row = cur.fetchone()
            _employee_amka_cols = row is not None and row[0] is not None
    except Exception:
        _employee_amka_cols = False
    return _employee_amka_cols


def _employee_identity_select() -> str:
    if employee_amka_columns_available():
        return ", emp.amka, emp.amika"
    return ", CAST(NULL AS nvarchar(11)) AS amka, CAST(NULL AS nvarchar(20)) AS amika"


def normalize_amka(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())[:11]
    return digits or None


def normalize_amika(value: Any) -> str | None:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())[:20]
    return digits or None


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
            emp.id, emp.afm, emp.eponymo, emp.onoma, emp.flex_arrival_minutes
            {_employee_identity_select()},
            e.active, e.hire_date, e.departure_date, e.catering_override,
            CASE WHEN NULLIF(e.work_time_qr_data_url, N'') IS NULL THEN CAST(0 AS bit) ELSE CAST(1 AS bit) END AS has_work_time_qr,
            CAST(e.work_time_qr_synced_at AS datetime2) AS work_time_qr_synced_at,
            p.code_aa AS parartima_aa,
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


def update_employment_catering_override(
    employer_afm: str, branch_aa: str, employee_afm: str,
    *, catering_override: bool | None,
) -> None:
    """Override catering-sector detection for one store employment."""
    with cursor() as cur:
        cur.execute(
            """
            UPDATE e SET catering_override=?, updated_at=SYSDATETIMEOFFSET()
            FROM dbo.karta_employment e
            JOIN dbo.karta_employee emp ON emp.id=e.employee_id
            JOIN dbo.karta_employer em ON em.id=e.employer_id
            LEFT JOIN dbo.karta_parartima p ON p.id=e.parartima_id
            WHERE em.afm=? AND emp.afm=? AND p.code_aa=?
            """,
            (catering_override, norm_afm(employer_afm), norm_afm(employee_afm),
             str(branch_aa or "0")),
        )
        if not cur.rowcount:
            raise ValueError("Δεν βρέθηκε η εργασιακή σύνδεση του εργαζομένου στο κατάστημα")


def update_employment_work_time_qr(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    *,
    qr_data_url: str | None,
) -> bool:
    """Αποθηκεύει το QR ψηφιακής οργάνωσης στη σύνδεση εργαζόμενου-καταστήματος."""
    data_url = (qr_data_url or "").strip()
    if not data_url:
        return False
    with cursor() as cur:
        cur.execute(
            """
            UPDATE e
            SET work_time_qr_data_url=?,
                work_time_qr_synced_at=SYSDATETIMEOFFSET(),
                updated_at=SYSDATETIMEOFFSET()
            FROM dbo.karta_employment e
            JOIN dbo.karta_employee emp ON emp.id=e.employee_id
            JOIN dbo.karta_employer em ON em.id=e.employer_id
            LEFT JOIN dbo.karta_parartima p ON p.id=e.parartima_id
            WHERE em.afm=? AND emp.afm=? AND p.code_aa=?
            """,
            (
                data_url,
                norm_afm(employer_afm),
                norm_afm(employee_afm),
                str(branch_aa or "0").strip()[:32] or "0",
            ),
        )
        return bool(cur.rowcount)


def get_employment_work_time_qr(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
) -> dict[str, Any] | None:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    e_afm = norm_afm(employee_afm)
    if not e_afm:
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1)
                emp.afm AS employee_afm,
                emp.eponymo,
                emp.onoma,
                em.afm AS employer_afm,
                em.eponimia AS employer_eponimia,
                p.code_aa AS branch_aa,
                p.description AS branch_desc,
                e.work_time_qr_data_url,
                CAST(e.work_time_qr_synced_at AS datetime2) AS work_time_qr_synced_at
            FROM dbo.karta_employment e
            JOIN dbo.karta_employee emp ON emp.id=e.employee_id
            JOIN dbo.karta_employer em ON em.id=e.employer_id
            LEFT JOIN dbo.karta_parartima p ON p.id=e.parartima_id
            WHERE em.afm=? AND emp.afm=? AND p.code_aa=?
            ORDER BY e.active DESC, e.updated_at DESC
            """,
            (afm, e_afm, aa),
        )
        rows = rows_to_dicts(cur)
        return rows[0] if rows else None


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


def get_employee_row_by_afm(employee_afm: str) -> dict[str, Any] | None:
    afm = norm_afm(employee_afm)
    if not afm:
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT emp.afm, emp.eponymo, emp.onoma, emp.flex_arrival_minutes
                {_employee_identity_select()}
            FROM dbo.karta_employee emp
            WHERE emp.afm = ?
            """,
            (afm,),
        )
        rows = rows_to_dicts(cur)
        return rows[0] if rows else None


def upsert_employee_by_afm(
    afm: str,
    eponymo: str | None,
    onoma: str | None,
    *,
    flex_arrival_minutes: int | None = None,
    amka: str | None = None,
    amika: str | None = None,
) -> int | None:
    """Δημιουργία/ενημέρωση εργαζόμενου από ΑΦΜ (π.χ. μετά από portal ωράριο)."""
    ep = (eponymo or "").strip()[:200] or None
    on = (onoma or "").strip()[:200] or None
    amka_n = normalize_amka(amka)
    amika_n = normalize_amika(amika)
    if not norm_afm(afm):
        return None
    if not ep and not on and flex_arrival_minutes is None and not amka_n and not amika_n:
        return None
    with cursor() as cur:
        return upsert_employee(
            cur, afm, ep, on,
            flex_arrival_minutes=flex_arrival_minutes,
            amka=amka_n,
            amika=amika_n,
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


def list_afms_needing_employment_enrichment(
    employer_afm: str, branch_aa: str
) -> list[str]:
    """ΑΦΜ που χρειάζονται Μητρώο/QR: στο ωράριο χωρίς σύνδεση/QR, ή ενεργοί χωρίς QR.

    Χωρίς σύνδεση `karta_employment` ο scanner δεν τους αναγνωρίζει· χωρίς QR
    λείπει η κάρτα εργασίας στο UI / τοπικό αντίγραφο από το portal.
    """
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    with cursor(commit=False) as cur:
        cur.execute(
            """
            WITH sched AS (
                SELECT DISTINCT LTRIM(RTRIM(employee_afm)) AS employee_afm
                FROM dbo.karta_schedule
                WHERE employer_afm=? AND branch_aa=?
                  AND employee_afm IS NOT NULL AND LTRIM(RTRIM(employee_afm)) <> N''
                  -- Μόνο πρόσφατο ωράριο: παλιά ορφανά δεν είναι στο τρέχον Μητρώο.
                  AND TRY_CONVERT(date, work_date, 103) >= DATEADD(
                      day, -14, CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'GTB Standard Time' AS date)
                  )
            ),
            from_schedule AS (
                SELECT s.employee_afm
                FROM sched s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM dbo.karta_employment e
                    INNER JOIN dbo.karta_employee emp ON emp.id = e.employee_id
                    INNER JOIN dbo.karta_employer em ON em.id = e.employer_id
                    LEFT JOIN dbo.karta_parartima p ON p.id = e.parartima_id
                    WHERE emp.afm = s.employee_afm
                      AND em.afm = ?
                      AND p.code_aa = ?
                      AND e.active = 1
                )
                OR EXISTS (
                    SELECT 1
                    FROM dbo.karta_employment e
                    INNER JOIN dbo.karta_employee emp ON emp.id = e.employee_id
                    INNER JOIN dbo.karta_employer em ON em.id = e.employer_id
                    LEFT JOIN dbo.karta_parartima p ON p.id = e.parartima_id
                    WHERE emp.afm = s.employee_afm
                      AND em.afm = ?
                      AND p.code_aa = ?
                      AND e.active = 1
                      AND NULLIF(e.work_time_qr_data_url, N'') IS NULL
                )
            ),
            from_active AS (
                SELECT emp.afm AS employee_afm
                FROM dbo.karta_employment e
                INNER JOIN dbo.karta_employee emp ON emp.id = e.employee_id
                INNER JOIN dbo.karta_employer em ON em.id = e.employer_id
                LEFT JOIN dbo.karta_parartima p ON p.id = e.parartima_id
                WHERE em.afm = ?
                  AND p.code_aa = ?
                  AND e.active = 1
                  AND NULLIF(e.work_time_qr_data_url, N'') IS NULL
            )
            SELECT employee_afm FROM (
                SELECT employee_afm FROM from_schedule
                UNION
                SELECT employee_afm FROM from_active
            ) u
            ORDER BY employee_afm
            """,
            (afm, aa, afm, aa, afm, aa, afm, aa),
        )
        out: list[str] = []
        for row in cur.fetchall():
            value = norm_afm(row[0] if not isinstance(row, dict) else row.get("employee_afm"))
            if value:
                out.append(value)
        return out


def link_employee_to_store(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    *,
    flex_arrival_minutes: int | None = None,
    amka: str | None = None,
    amika: str | None = None,
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
            amka=amka,
            amika=amika,
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
    amka: str | None = None,
    amika: str | None = None,
) -> int | None:
    a = norm_afm(afm)
    amka_n = normalize_amka(amka)
    amika_n = normalize_amika(amika)
    identity = employee_amka_columns_available()
    cur.execute("SELECT id FROM dbo.karta_employee WHERE afm = ?", (a,))
    row = cur.fetchone()
    if row:
        sets = [
            "eponymo = COALESCE(NULLIF(?, ''), eponymo)",
            "onoma = COALESCE(NULLIF(?, ''), onoma)",
        ]
        params: list[Any] = [eponymo or "", onoma or ""]
        if flex_arrival_minutes is not None:
            sets.append("flex_arrival_minutes = ?")
            params.append(int(flex_arrival_minutes))
        if identity and amka_n:
            sets.append("amka = ?")
            params.append(amka_n)
        if identity and amika_n:
            sets.append("amika = ?")
            params.append(amika_n)
        sets.append("updated_at = SYSDATETIMEOFFSET()")
        params.append(int(row[0]))
        cur.execute(
            f"UPDATE dbo.karta_employee SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        return int(row[0])
    if identity:
        cur.execute(
            """
            INSERT INTO dbo.karta_employee (afm, eponymo, onoma, flex_arrival_minutes, amka, amika)
            OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?)
            """,
            (a, eponymo, onoma, flex_arrival_minutes, amka_n, amika_n),
        )
    else:
        cur.execute(
            """
            INSERT INTO dbo.karta_employee (afm, eponymo, onoma, flex_arrival_minutes)
            OUTPUT INSERTED.id VALUES (?, ?, ?, ?)
            """,
            (a, eponymo, onoma, flex_arrival_minutes),
        )
    ins = cur.fetchone()
    return int(ins[0]) if ins else None


def fill_employment_hire_date_if_empty(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    hire_date: date,
) -> bool:
    """Γράφει ημερομηνία πρόσληψης Ergani μόνο αν το τοπικό πεδίο είναι κενό."""
    if hire_date is None:
        return False
    afm = norm_afm(employer_afm)
    e_afm = norm_afm(employee_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    with cursor() as cur:
        cur.execute(
            """
            UPDATE e SET hire_date=?, updated_at=SYSDATETIMEOFFSET()
            FROM dbo.karta_employment e
            JOIN dbo.karta_employee emp ON emp.id=e.employee_id
            JOIN dbo.karta_employer em ON em.id=e.employer_id
            LEFT JOIN dbo.karta_parartima p ON p.id=e.parartima_id
            WHERE em.afm=? AND emp.afm=? AND e.hire_date IS NULL
              AND ISNULL(p.code_aa, N'0') = ?
            """,
            (hire_date, afm, e_afm, aa),
        )
        if cur.rowcount:
            return True
        cur.execute(
            """
            UPDATE e SET hire_date=?, updated_at=SYSDATETIMEOFFSET()
            FROM dbo.karta_employment e
            JOIN dbo.karta_employee emp ON emp.id=e.employee_id
            JOIN dbo.karta_employer em ON em.id=e.employer_id
            WHERE em.afm=? AND emp.afm=? AND e.hire_date IS NULL
            """,
            (hire_date, afm, e_afm),
        )
        return bool(cur.rowcount)


def upsert_employment(
    cur: pyodbc.Cursor,
    employer_id: int,
    employee_id: int,
    parartima_id: int | None,
    *,
    hire_date: date | None = None,
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
        if hire_date is not None:
            cur.execute(
                """
                UPDATE dbo.karta_employment
                SET parartima_id = ?, active = 1, updated_at = SYSDATETIMEOFFSET(),
                    hire_date = COALESCE(hire_date, ?)
                WHERE id = ?
                """,
                (parartima_id, hire_date, int(row[0])),
            )
        else:
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
        INSERT INTO dbo.karta_employment (
            employer_id, employee_id, parartima_id, active, hire_date
        )
        VALUES (?, ?, ?, 1, ?)
        """,
        (employer_id, employee_id, parartima_id, hire_date),
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
