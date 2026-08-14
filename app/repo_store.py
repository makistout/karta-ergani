"""Καταστήματα (λογιστικό γραφείο) — pyodbc."""

from __future__ import annotations

from typing import Any

from app.db import cursor
from app.row_util import row_to_dict, rows_to_dicts

_sync_meta_cols: bool | None = None
_action_settings_cols: bool | None = None
_notify_grace_col: bool | None = None
_fixed_exit_col: bool | None = None
_sunday_rest_transfer_col: bool | None = None


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


def action_settings_columns_available() -> bool:
    """True αν υπάρχουν οι στήλες αυτόματων ενεργειών στο κατάστημα."""
    global _action_settings_cols
    if _action_settings_cols is True:
        return _action_settings_cols
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                "SELECT COL_LENGTH(N'dbo.karta_store_config', N'auto_close_prev_day_enabled')"
            )
            row = cur.fetchone()
            _action_settings_cols = row is not None and row[0] is not None
    except Exception:
        _action_settings_cols = False
    return _action_settings_cols


def notify_grace_column_available() -> bool:
    global _notify_grace_col
    if _notify_grace_col is True:
        return _notify_grace_col
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                "SELECT COL_LENGTH(N'dbo.karta_store_config', N'notify_grace_minutes')"
            )
            row = cur.fetchone()
            _notify_grace_col = row is not None and row[0] is not None
    except Exception:
        _notify_grace_col = False
    return _notify_grace_col


def fixed_exit_column_available() -> bool:
    global _fixed_exit_col
    if _fixed_exit_col is True:
        return _fixed_exit_col
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                "SELECT COL_LENGTH(N'dbo.karta_store_config', N'auto_close_fixed_exit_time')"
            )
            row = cur.fetchone()
            _fixed_exit_col = row is not None and row[0] is not None
    except Exception:
        _fixed_exit_col = False
    return _fixed_exit_col


def sunday_rest_transfer_column_available() -> bool:
    global _sunday_rest_transfer_col
    if _sunday_rest_transfer_col is True:
        return _sunday_rest_transfer_col
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                "SELECT COL_LENGTH(N'dbo.karta_store_config', N'sunday_rest_transfer_enabled')"
            )
            row = cur.fetchone()
            _sunday_rest_transfer_col = row is not None and row[0] is not None
    except Exception:
        _sunday_rest_transfer_col = False
    return _sunday_rest_transfer_col


def get_sunday_rest_transfer_enabled(store_id: int) -> bool:
    if not sunday_rest_transfer_column_available():
        return False
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT CAST(sunday_rest_transfer_enabled AS int)
            FROM dbo.karta_store_config
            WHERE id = ?
            """,
            (int(store_id),),
        )
        row = cur.fetchone()
        return bool(row and int(row[0] or 0))


def get_notify_grace_minutes(store_id: int) -> int:
    from app.today_notify_logic import NOTIFY_GRACE_MINUTES, normalize_notify_grace_minutes

    if not notify_grace_column_available():
        return NOTIFY_GRACE_MINUTES
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT notify_grace_minutes
            FROM dbo.karta_store_config
            WHERE id = ?
            """,
            (int(store_id),),
        )
        row = cur.fetchone()
        if not row:
            return NOTIFY_GRACE_MINUTES
        return normalize_notify_grace_minutes(row[0])


def _store_action_select_extra() -> str:
    if action_settings_columns_available():
        fixed = (
            ", auto_close_fixed_exit_time"
            if fixed_exit_column_available()
            else ", CAST(NULL AS nvarchar(5)) AS auto_close_fixed_exit_time"
        )
        return f"""
               CAST(auto_close_prev_day_enabled AS int) AS auto_close_prev_day_enabled,
               auto_close_prev_day_time,
               auto_close_prev_day_last_run_date
               {fixed}
        """
    return """
               CAST(0 AS int) AS auto_close_prev_day_enabled,
               CAST(N'00:30' AS nvarchar(5)) AS auto_close_prev_day_time,
               CAST(NULL AS nvarchar(10)) AS auto_close_prev_day_last_run_date,
               CAST(NULL AS nvarchar(5)) AS auto_close_fixed_exit_time
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
               {_store_sync_select_extra()},
               {_store_action_select_extra()}
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
               {_store_sync_select_extra()},
               {_store_action_select_extra()}
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


def touch_protocol_sync(store_id: int) -> None:
    sid = int(store_id)
    with cursor() as cur:
        try:
            cur.execute(
                """
                UPDATE dbo.karta_store_config
                SET protocol_last_sync_at = SYSDATETIMEOFFSET(),
                    last_sync_at = SYSDATETIMEOFFSET(),
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                sid,
            )
        except pyodbc.Error as exc:
            if "protocol_last_sync_at" not in str(exc):
                raise
            touch_last_sync(sid)


def effective_schedule_sync_at(cfg: dict[str, Any]) -> Any:
    return cfg.get("schedule_last_sync_at") or cfg.get("last_sync_at")


def effective_work_log_sync_at(cfg: dict[str, Any]) -> Any:
    return cfg.get("work_log_last_sync_at") or cfg.get("last_sync_at")


def get_action_settings(store_id: int) -> dict[str, Any]:
    if not action_settings_columns_available():
        return {
            "auto_close_prev_day_enabled": False,
            "auto_close_prev_day_time": "00:30",
            "auto_close_prev_day_last_run_date": None,
            "auto_close_fixed_exit_time": None,
            "notify_grace_minutes": 15,
            "sunday_rest_transfer_enabled": False,
            "db_setup": "sql/alter_add_store_action_settings.sql",
        }
    with cursor(commit=False) as cur:
        grace_sql = (
            ", notify_grace_minutes"
            if notify_grace_column_available()
            else ", CAST(15 AS int) AS notify_grace_minutes"
        )
        fixed_sql = (
            ", auto_close_fixed_exit_time"
            if fixed_exit_column_available()
            else ", CAST(NULL AS nvarchar(5)) AS auto_close_fixed_exit_time"
        )
        rest_sql = (
            ", CAST(sunday_rest_transfer_enabled AS int) AS sunday_rest_transfer_enabled"
            if sunday_rest_transfer_column_available()
            else ", CAST(0 AS int) AS sunday_rest_transfer_enabled"
        )
        cur.execute(
            f"""
            SELECT
                CAST(auto_close_prev_day_enabled AS int) AS auto_close_prev_day_enabled,
                auto_close_prev_day_time,
                auto_close_prev_day_last_run_date
                {fixed_sql}
                {grace_sql}
                {rest_sql}
            FROM dbo.karta_store_config
            WHERE id = ?
            """,
            (int(store_id),),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Δεν βρέθηκε κατάστημα id={store_id}")
        data = row_to_dict(cur, row)
    grace = 15
    if notify_grace_column_available():
        from app.today_notify_logic import normalize_notify_grace_minutes

        grace = normalize_notify_grace_minutes(data.get("notify_grace_minutes"))
    from app.auto_close_cards import normalize_optional_auto_close_time

    out = {
        "auto_close_prev_day_enabled": bool(data.get("auto_close_prev_day_enabled")),
        "auto_close_prev_day_time": data.get("auto_close_prev_day_time") or "00:30",
        "auto_close_prev_day_last_run_date": data.get("auto_close_prev_day_last_run_date"),
        "auto_close_fixed_exit_time": normalize_optional_auto_close_time(
            data.get("auto_close_fixed_exit_time")
        ),
        "notify_grace_minutes": grace,
        "sunday_rest_transfer_enabled": bool(int(data.get("sunday_rest_transfer_enabled") or 0)),
    }
    if not notify_grace_column_available():
        out["db_setup_notify_grace"] = "sql/alter_add_store_notify_grace_minutes.sql"
    if not fixed_exit_column_available():
        out["db_setup_fixed_exit"] = "sql/alter_add_auto_close_fixed_exit_time.sql"
    if not sunday_rest_transfer_column_available():
        out["db_setup_sunday_rest_transfer"] = "sql/alter_add_store_sunday_rest_transfer.sql"
    return out


def save_action_settings(
    store_id: int,
    *,
    auto_close_prev_day_enabled: bool,
    auto_close_prev_day_time: str,
    auto_close_fixed_exit_time: str | None = None,
    notify_grace_minutes: int | None = None,
    sunday_rest_transfer_enabled: bool | None = None,
) -> dict[str, Any]:
    if not action_settings_columns_available():
        raise RuntimeError("Λείπει migration: sql/alter_add_store_action_settings.sql")
    from app.auto_close_cards import normalize_optional_auto_close_time
    from app.today_notify_logic import normalize_notify_grace_minutes

    time_s = str(auto_close_prev_day_time or "").strip()[:5] or "00:30"
    fixed_s = normalize_optional_auto_close_time(auto_close_fixed_exit_time)
    grace = normalize_notify_grace_minutes(notify_grace_minutes)
    rest_enabled = bool(sunday_rest_transfer_enabled)
    sets = [
        "auto_close_prev_day_enabled = ?",
        "auto_close_prev_day_time = ?",
        "updated_at = SYSDATETIMEOFFSET()",
    ]
    params: list[Any] = [1 if auto_close_prev_day_enabled else 0, time_s]
    if fixed_exit_column_available():
        sets.insert(2, "auto_close_fixed_exit_time = ?")
        params.append(fixed_s)
    if notify_grace_column_available():
        sets.insert(-1, "notify_grace_minutes = ?")
        params.append(grace)
    if sunday_rest_transfer_column_available():
        sets.insert(-1, "sunday_rest_transfer_enabled = ?")
        params.append(1 if rest_enabled else 0)
    params.append(int(store_id))
    with cursor() as cur:
        cur.execute(
            f"""
            UPDATE dbo.karta_store_config
            SET {", ".join(sets)}
            WHERE id = ?
            """,
            tuple(params),
        )
    return get_action_settings(store_id)


def mark_auto_close_prev_day_run(store_id: int, work_date_iso: str) -> None:
    if not action_settings_columns_available():
        return
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_store_config
            SET auto_close_prev_day_last_run_date = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            (str(work_date_iso or "").strip()[:10], int(store_id)),
        )
