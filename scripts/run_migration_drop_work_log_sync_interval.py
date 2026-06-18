"""Εκτέλεση sql/alter_drop_work_log_sync_interval.sql (idempotent)."""
from __future__ import annotations

import sys
from pathlib import Path

import pyodbc

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import Config


def col_exists(cur: pyodbc.Cursor) -> bool:
    cur.execute(
        "SELECT COL_LENGTH(N'dbo.karta_store_config', N'work_log_sync_interval_minutes')"
    )
    row = cur.fetchone()
    return row is not None and row[0] is not None


def main() -> None:
    sql_path = _ROOT / "sql" / "alter_drop_work_log_sync_interval.sql"
    conn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    cur = conn.cursor()
    if not col_exists(cur):
        print("ALREADY_APPLIED")
        return
    print("BEFORE: work_log_sync_interval_minutes exists")
    raw = sql_path.read_text(encoding="utf-8")
    batches = [b.strip() for b in raw.split("\nGO\n") if b.strip()]
    for i, batch in enumerate(batches, 1):
        if not batch or batch.startswith("/*"):
            continue
        print(f"Batch {i}...")
        cur.execute(batch)
    if col_exists(cur):
        raise SystemExit("Migration incomplete — column still exists")
    print("OK: work_log_sync_interval_minutes removed")


if __name__ == "__main__":
    main()
