"""Αποθήκευση και ανάκτηση sync logs από MSSQL."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pyodbc

from app.db import cursor

_RUN_TABLE = "karta_sync_run"
_LOG_TABLE = "karta_sync_log"


def tables_available() -> bool:
    try:
        with cursor() as cur:
            cur.execute(
                "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = N'dbo' "
                f"AND TABLE_NAME = N'{_LOG_TABLE}'"
            )
            return cur.fetchone() is not None
    except pyodbc.Error:
        return False


def create_run(
    run_id: str,
    *,
    operation: str,
    store_id: int | None = None,
) -> None:
    if not tables_available():
        return
    try:
        with cursor() as cur:
            cur.execute(
                f"""
                IF NOT EXISTS (SELECT 1 FROM dbo.{_RUN_TABLE} WHERE run_id = ?)
                INSERT INTO dbo.{_RUN_TABLE} (run_id, store_id, operation, status)
                VALUES (?, ?, ?, N'running')
                """,
                run_id,
                run_id,
                store_id,
                operation,
            )
    except pyodbc.Error:
        pass


def update_run_progress(
    run_id: str,
    *,
    message: str | None = None,
    step: int | None = None,
    total: int | None = None,
) -> None:
    if not tables_available():
        return
    sets: list[str] = []
    params: list[Any] = []
    if message is not None:
        sets.append("message = ?")
        params.append(message[:500])
    if step is not None:
        sets.append("step = ?")
        params.append(int(step))
    if total is not None:
        sets.append("total = ?")
        params.append(int(total))
    if not sets:
        return
    params.append(run_id)
    try:
        with cursor() as cur:
            cur.execute(
                f"UPDATE dbo.{_RUN_TABLE} SET {', '.join(sets)} WHERE run_id = ?",
                *params,
            )
    except pyodbc.Error:
        pass


def finish_run(
    run_id: str,
    *,
    status: str,
    message: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    if not tables_available():
        return
    result_json = None
    if result is not None:
        try:
            result_json = json.dumps(result, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            result_json = None
    try:
        with cursor() as cur:
            cur.execute(
                f"""
                UPDATE dbo.{_RUN_TABLE}
                SET status = ?, message = COALESCE(?, message),
                    result_json = COALESCE(?, result_json),
                    finished_at = SYSDATETIMEOFFSET()
                WHERE run_id = ?
                """,
                status[:16],
                message[:500] if message else None,
                result_json,
                run_id,
            )
    except pyodbc.Error:
        pass


def append_line(
    run_id: str,
    seq: int,
    level: str,
    message: str,
    fields: dict[str, Any] | None = None,
) -> None:
    if not tables_available():
        return
    fields_json = None
    if fields:
        try:
            fields_json = json.dumps(fields, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            fields_json = None
    try:
        with cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO dbo.{_LOG_TABLE}
                    (run_id, seq, level, message, fields_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                run_id,
                int(seq),
                level[:8],
                message,
                fields_json,
            )
    except pyodbc.Error:
        pass


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")[:32])
    except (TypeError, ValueError):
        return None


_DURATION_SQL = """
    CASE
        WHEN r.finished_at IS NOT NULL
        THEN DATEDIFF(SECOND, r.started_at, r.finished_at)
        WHEN LOWER(RTRIM(r.status)) = N'running'
        THEN DATEDIFF(SECOND, r.started_at, SYSDATETIMEOFFSET())
        ELSE NULL
    END AS duration_seconds
"""


def _enrich_run_timing(item: dict[str, Any]) -> None:
    raw_duration = item.pop("_duration_seconds", None)
    if raw_duration is not None:
        try:
            item["duration_seconds"] = max(0, int(raw_duration))
        except (TypeError, ValueError):
            pass
    if item.get("duration_seconds") is None:
        started = _parse_iso_dt(item.get("started_at"))
        finished = _parse_iso_dt(item.get("finished_at"))
        if started and finished:
            item["duration_seconds"] = max(0, int((finished - started).total_seconds()))
        elif started and str(item.get("status") or "").lower() == "running":
            now = datetime.now(started.tzinfo) if started.tzinfo else datetime.now()
            item["duration_seconds"] = max(0, int((now - started).total_seconds()))
    if str(item.get("status") or "").lower() == "running":
        item["in_progress"] = True


def reconcile_stale_runs() -> int:
    """Runs που έμειναν 'running' — διόρθωση από logs ή ηλικία."""
    if not tables_available():
        return 0
    total = 0
    statements = [
        # 1) Ξεκάθαρο μήνυμα ολοκλήρωσης στα logs
        f"""
        UPDATE r
        SET status = N'done',
            finished_at = COALESCE(r.finished_at, sub.last_ts),
            message = COALESCE(NULLIF(r.message, N''), sub.done_msg)
        FROM dbo.{_RUN_TABLE} r
        INNER JOIN (
            SELECT l.run_id,
                   MAX(l.created_at) AS last_ts,
                   MAX(CASE
                       WHEN l.message LIKE N'%Ολοκλήρωση%'
                            OR l.message LIKE N'%Ολοκληρώθηκε%'
                       THEN l.message
                   END) AS done_msg
            FROM dbo.{_LOG_TABLE} l
            GROUP BY l.run_id
        ) sub ON sub.run_id = r.run_id
        WHERE LOWER(RTRIM(r.status)) = N'running'
          AND sub.done_msg IS NOT NULL
        """,
        # 2) Έχει logs, τελευταία δραστηριότητα πριν 5+ λεπτά
        f"""
        UPDATE r
        SET status = CASE
                WHEN sub.has_error > 0 THEN N'error'
                ELSE N'done'
            END,
            finished_at = COALESCE(r.finished_at, sub.last_ts),
            message = COALESCE(
                NULLIF(r.message, N''),
                tail.last_msg,
                N'Ολοκληρώθηκε (αυτόματη διόρθωση κατάστασης)'
            )
        FROM dbo.{_RUN_TABLE} r
        INNER JOIN (
            SELECT l.run_id,
                   MAX(l.created_at) AS last_ts,
                   SUM(CASE WHEN LOWER(l.level) = N'error' THEN 1 ELSE 0 END) AS has_error
            FROM dbo.{_LOG_TABLE} l
            GROUP BY l.run_id
        ) sub ON sub.run_id = r.run_id
        OUTER APPLY (
            SELECT TOP 1 l2.message AS last_msg
            FROM dbo.{_LOG_TABLE} l2
            WHERE l2.run_id = r.run_id
            ORDER BY l2.created_at DESC, l2.seq DESC
        ) tail
        WHERE LOWER(RTRIM(r.status)) = N'running'
          AND sub.last_ts < DATEADD(MINUTE, -5, SYSDATETIMEOFFSET())
          AND r.started_at < DATEADD(MINUTE, -5, SYSDATETIMEOFFSET())
        """,
        # 3) Χωρίς logs, παλιότερο από 10 λεπτά
        f"""
        UPDATE r
        SET status = N'error',
            finished_at = COALESCE(r.finished_at, SYSDATETIMEOFFSET()),
            message = COALESCE(
                NULLIF(r.message, N''),
                N'Διακόπηκε χωρίς καταγραφή ολοκλήρωσης'
            )
        FROM dbo.{_RUN_TABLE} r
        WHERE LOWER(RTRIM(r.status)) = N'running'
          AND r.started_at < DATEADD(MINUTE, -10, SYSDATETIMEOFFSET())
          AND NOT EXISTS (
              SELECT 1 FROM dbo.{_LOG_TABLE} l WHERE l.run_id = r.run_id
          )
        """,
    ]
    try:
        with cursor() as cur:
            for sql in statements:
                cur.execute(sql)
                total += int(cur.rowcount or 0)
    except pyodbc.Error:
        return total
    return total


def count_runs(*, store_id: int | None = None) -> int:
    if not tables_available():
        return 0
    try:
        with cursor() as cur:
            if store_id is not None:
                cur.execute(
                    f"SELECT COUNT(*) FROM dbo.{_RUN_TABLE} WHERE store_id = ?",
                    int(store_id),
                )
            else:
                cur.execute(f"SELECT COUNT(*) FROM dbo.{_RUN_TABLE}")
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except pyodbc.Error:
        return 0


def list_runs(
    *,
    store_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not tables_available():
        return []
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    try:
        with cursor() as cur:
            if store_id is not None:
                cur.execute(
                    f"""
                    SELECT r.run_id, r.store_id, r.operation, r.status, r.message,
                           r.step, r.total,
                           CAST(r.started_at AS DATETIME2) AS started_at,
                           CAST(r.finished_at AS DATETIME2) AS finished_at,
                           s.name AS store_name,
                           {_DURATION_SQL}
                    FROM dbo.{_RUN_TABLE} r
                    LEFT JOIN dbo.karta_store_config s ON s.id = r.store_id
                    WHERE r.store_id = ?
                    ORDER BY r.started_at DESC
                    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                    """,
                    int(store_id),
                    off,
                    lim,
                )
            else:
                cur.execute(
                    f"""
                    SELECT r.run_id, r.store_id, r.operation, r.status, r.message,
                           r.step, r.total,
                           CAST(r.started_at AS DATETIME2) AS started_at,
                           CAST(r.finished_at AS DATETIME2) AS finished_at,
                           s.name AS store_name,
                           {_DURATION_SQL}
                    FROM dbo.{_RUN_TABLE} r
                    LEFT JOIN dbo.karta_store_config s ON s.id = r.store_id
                    ORDER BY r.started_at DESC
                    OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                    """,
                    off,
                    lim,
                )
            rows = cur.fetchall()
    except pyodbc.Error:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        item: dict[str, Any] = {
            "run_id": row[0],
            "store_id": row[1],
            "operation": row[2],
            "status": row[3],
            "message": row[4],
            "step": row[5],
            "total": row[6],
        }
        if row[7] is not None:
            item["started_at"] = (
                row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7])
            )
        if row[8] is not None:
            item["finished_at"] = (
                row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8])
            )
        if row[9]:
            item["store_name"] = row[9]
        if row[10] is not None:
            item["_duration_seconds"] = row[10]
        _enrich_run_timing(item)
        out.append(item)
    return out


def get_run(run_id: str) -> dict[str, Any] | None:
    if not tables_available():
        return None
    try:
        with cursor() as cur:
            cur.execute(
                f"""
                SELECT r.run_id, r.store_id, r.operation, r.status, r.message,
                       r.step, r.total,
                       CAST(r.started_at AS DATETIME2) AS started_at,
                       CAST(r.finished_at AS DATETIME2) AS finished_at,
                       r.result_json,
                       s.name AS store_name,
                       {_DURATION_SQL}
                FROM dbo.{_RUN_TABLE} r
                LEFT JOIN dbo.karta_store_config s ON s.id = r.store_id
                WHERE r.run_id = ?
                """,
                run_id,
            )
            row = cur.fetchone()
    except pyodbc.Error:
        return None
    if not row:
        return None
    item: dict[str, Any] = {
        "run_id": row[0],
        "store_id": row[1],
        "operation": row[2],
        "status": row[3],
        "message": row[4],
        "step": row[5],
        "total": row[6],
    }
    if row[7] is not None:
        item["started_at"] = (
            row[7].isoformat() if hasattr(row[7], "isoformat") else str(row[7])
        )
    if row[8] is not None:
        item["finished_at"] = (
            row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8])
        )
    if row[9]:
        try:
            item["result"] = json.loads(row[9])
        except json.JSONDecodeError:
            item["result_raw"] = row[9]
    if row[10]:
        item["store_name"] = row[10]
    if row[11] is not None:
        item["_duration_seconds"] = row[11]
    item["lines"] = list_lines(run_id, limit=500)
    _enrich_run_timing(item)
    return item


def list_lines(run_id: str, limit: int = 150) -> list[dict[str, Any]]:
    if not tables_available():
        return []
    lim = max(1, min(int(limit), 500))
    try:
        with cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP (?) seq, level, message, fields_json,
                       CAST(created_at AS DATETIME2) AS created_at
                FROM dbo.{_LOG_TABLE}
                WHERE run_id = ?
                ORDER BY seq DESC
                """,
                lim,
                run_id,
            )
            rows = cur.fetchall()
    except pyodbc.Error:
        return []
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        item: dict[str, Any] = {
            "seq": row[0],
            "level": row[1],
            "message": row[2],
        }
        if row[3]:
            try:
                item["fields"] = json.loads(row[3])
            except json.JSONDecodeError:
                pass
        if row[4] is not None:
            item["ts"] = row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4])
        out.append(item)
    return out
