"""Καταστήματα (λογιστικό γραφείο) — pyodbc."""

from __future__ import annotations

from typing import Any

from app.db import cursor
from app.row_util import row_to_dict, rows_to_dicts

_sync_meta_cols: bool | None = None


def sync_meta_columns_available() -> bool:
    """True αν έχει τρέξει sql/alter_add_store_sync_timestamps.sql."""
    global _sync_meta_cols
    if _sync_meta_cols is not None:
        return _sync_meta_cols
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                "SELECT COL_LENGTH(N'dbo.karta_store_config', N'work_log_last_sync_at')"
            )
            row = cur.fetchone()
            _sync_meta_cols = row is not None and row[0] is not None
    except Exception:
        _sync_meta_cols = False
    return _sync_meta_cols


def _store_sync_select_extra() -> str:
    if sync_meta_columns_available():
        return """
               CAST(schedule_last_sync_at AS datetime2) AS schedule_last_sync_at,
               CAST(work_log_last_sync_at AS datetime2) AS work_log_last_sync_at
        """
    return """
               CAST(last_sync_at AS datetime2) AS schedule_last_sync_at,
               CAST(last_sync_at AS datetime2) AS work_log_last_sync_at
    """


def list_store_configs() -> list[dict[str, Any]]:
    sql = f"""
        SELECT id, name, username, password, usertype,
               web_username, web_password,
               employer_afm, branch_aa,
               ISNULL(ergani_env, N'production') AS ergani_env,
               sepe_code, sepe_desc, oaed_code, oaed_desc, kad_code, kad_desc,
               kallikratis_code, kallikratis_desc,
               CAST(updated_at AS datetime2) AS updated_at,
               CAST(last_sync_at AS datetime2) AS last_sync_at,
               {_store_sync_select_extra()}
        FROM dbo.karta_store_config
        ORDER BY name, id
    """
    with cursor(commit=False) as cur:
        cur.execute(sql)
        return rows_to_dicts(cur)


def list_store_employee_counts() -> dict[int, int]:
    sql = """
        SELECT s.id, COUNT(DISTINCT e.employee_id) AS employee_count
        FROM dbo.karta_store_config s
        LEFT JOIN dbo.karta_employer em ON em.afm = s.employer_afm
        LEFT JOIN dbo.karta_parartima p
            ON p.employer_id = em.id
           AND p.code_aa = s.branch_aa
        LEFT JOIN dbo.karta_employment e
            ON e.employer_id = em.id
           AND e.active = 1
           AND (
                p.id IS NULL
                OR e.parartima_id = p.id
           )
        GROUP BY s.id
    """
    with cursor(commit=False) as cur:
        cur.execute(sql)
        return {
            int(row[0]): int(row[1] or 0)
            for row in cur.fetchall()
        }


def get_store_config(store_id: int) -> dict[str, Any] | None:
    sql = f"""
        SELECT id, name, username, password, usertype,
               web_username, web_password,
               employer_afm, branch_aa,
               ISNULL(ergani_env, N'production') AS ergani_env,
               sepe_code, sepe_desc, oaed_code, oaed_desc, kad_code, kad_desc,
               kallikratis_code, kallikratis_desc,
               CAST(updated_at AS datetime2) AS updated_at,
               CAST(last_sync_at AS datetime2) AS last_sync_at,
               {_store_sync_select_extra()}
        FROM dbo.karta_store_config WHERE id = ?
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (int(store_id),))
        row = cur.fetchone()
        return row_to_dict(cur, row) if row else None


def get_store_by_afm(employer_afm: str, branch_aa: str = "0") -> dict[str, Any] | None:
    sql = """
        SELECT TOP (1) id, name, username, password, usertype,
               web_username, web_password,
               employer_afm, branch_aa,
               ISNULL(ergani_env, N'production') AS ergani_env,
               sepe_code, sepe_desc, oaed_code, oaed_desc, kad_code, kad_desc,
               kallikratis_code, kallikratis_desc
        FROM dbo.karta_store_config
        WHERE employer_afm = ? AND branch_aa = ?
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (str(employer_afm).strip(), str(branch_aa).strip()))
        row = cur.fetchone()
        return row_to_dict(cur, row) if row else None


def save_store_credentials(
    *,
    name: str,
    username: str,
    password: str,
    usertype: str,
    employer_afm: str,
    branch_aa: str = "0",
    ergani_env: str = "production",
    web_username: str | None = None,
    web_password: str | None = None,
    store_id: int | None = None,
) -> int:
    """Αποθήκευση/ενημέρωση διαπιστευτηρίων (βήμα 1 wizard)."""
    wu = (web_username or "").strip() or None
    wp = (web_password or "").strip() or None
    if store_id:
        existing = get_store_config(int(store_id))
        if not existing:
            raise ValueError(f"Δεν βρέθηκε κατάστημα id={store_id}")
        pwd = password or (existing.get("password") or "")
        if not wp:
            wp = existing.get("web_password")
        if not wu:
            wu = existing.get("web_username")
        sql = """
            UPDATE dbo.karta_store_config SET
                name = ?, username = ?, password = ?, usertype = ?,
                web_username = ?, web_password = ?,
                employer_afm = ?, branch_aa = ?, ergani_env = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
        """
        params = (
            name,
            username,
            pwd,
            usertype,
            wu,
            wp,
            employer_afm,
            branch_aa,
            ergani_env,
            int(store_id),
        )
        with cursor() as cur:
            cur.execute(sql, params)
        return int(store_id)

    sql = """
        INSERT INTO dbo.karta_store_config (
            name, username, password, usertype,
            web_username, web_password,
            employer_afm, branch_aa, ergani_env
        )
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        name, username, password, usertype, wu, wp,
        employer_afm, branch_aa, ergani_env,
    )
    with cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return int(row[0]) if row else 0


def save_store_config(
    *,
    name: str,
    username: str,
    password: str,
    usertype: str,
    employer_afm: str,
    branch_aa: str,
    sepe_code: str | None,
    sepe_desc: str | None,
    oaed_code: str | None,
    oaed_desc: str | None,
    kad_code: str | None,
    kad_desc: str | None,
    kallikratis_code: str | None,
    kallikratis_desc: str | None,
    ergani_env: str = "production",
    web_username: str | None = None,
    web_password: str | None = None,
    store_id: int | None = None,
) -> int:
    wu = (web_username or "").strip() or None
    wp = (web_password or "").strip() or None
    existing: dict[str, Any] | None = None
    if store_id:
        existing = get_store_config(int(store_id))
    if store_id:
        if existing:
            if not wp:
                wp = existing.get("web_password")
            if not wu:
                wu = existing.get("web_username")
        sql = """
            UPDATE dbo.karta_store_config SET
                name = ?, username = ?, password = ?, usertype = ?,
                web_username = ?, web_password = ?,
                employer_afm = ?, branch_aa = ?, ergani_env = ?,
                sepe_code = ?, sepe_desc = ?,
                oaed_code = ?, oaed_desc = ?,
                kad_code = ?, kad_desc = ?,
                kallikratis_code = ?, kallikratis_desc = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
        """
        params = (
            name, username, password, usertype, wu, wp,
            employer_afm, branch_aa, ergani_env,
            sepe_code, sepe_desc, oaed_code, oaed_desc, kad_code, kad_desc,
            kallikratis_code, kallikratis_desc, int(store_id),
        )
        with cursor() as cur:
            cur.execute(sql, params)
            return int(store_id)
    sql = """
        INSERT INTO dbo.karta_store_config (
            name, username, password, usertype,
            web_username, web_password,
            employer_afm, branch_aa, ergani_env,
            sepe_code, sepe_desc, oaed_code, oaed_desc, kad_code, kad_desc,
            kallikratis_code, kallikratis_desc
        )
        OUTPUT INSERTED.id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        name, username, password, usertype, wu, wp,
        employer_afm, branch_aa, ergani_env,
        sepe_code, sepe_desc, oaed_code, oaed_desc, kad_code, kad_desc,
        kallikratis_code, kallikratis_desc,
    )
    with cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return int(row[0]) if row else 0


def delete_store_config(store_id: int) -> None:
    with cursor() as cur:
        cur.execute("DELETE FROM dbo.karta_store_config WHERE id = ?", (int(store_id),))


def touch_last_sync(store_id: int) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_store_config
            SET last_sync_at = SYSDATETIMEOFFSET(), updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            (int(store_id),),
        )


def touch_schedule_sync(store_id: int) -> None:
    sid = int(store_id)
    if sync_meta_columns_available():
        with cursor() as cur:
            cur.execute(
                """
                UPDATE dbo.karta_store_config
                SET schedule_last_sync_at = SYSDATETIMEOFFSET(),
                    last_sync_at = SYSDATETIMEOFFSET(),
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                sid,
            )
    else:
        touch_last_sync(sid)


def touch_work_log_sync(store_id: int) -> None:
    sid = int(store_id)
    if sync_meta_columns_available():
        with cursor() as cur:
            cur.execute(
                """
                UPDATE dbo.karta_store_config
                SET work_log_last_sync_at = SYSDATETIMEOFFSET(),
                    last_sync_at = SYSDATETIMEOFFSET(),
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                sid,
            )
    else:
        touch_last_sync(sid)


def effective_schedule_sync_at(cfg: dict[str, Any]) -> Any:
    return cfg.get("schedule_last_sync_at") or cfg.get("last_sync_at")


def effective_work_log_sync_at(cfg: dict[str, Any]) -> Any:
    return cfg.get("work_log_last_sync_at") or cfg.get("last_sync_at")
