"""Αποθήκευση και ανάκτηση sync logs από MSSQL."""

from __future__ import annotations

import json
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


def list_lines(run_id: str, limit: int = 150) -> list[dict[str, Any]]:
    if not tables_available():
        return []
    lim = max(1, min(int(limit), 500))
    try:
        with cursor() as cur:
            cur.execute(
                f"""
                SELECT TOP (?) seq, level, message, fields_json, created_at
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
