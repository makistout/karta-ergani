"""Εκτέλεση sql/alter_add_store_sync_timestamps.sql (idempotent)."""
from __future__ import annotations

import sys
from pathlib import Path

import pyodbc

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import Config

_COLS = (
    "schedule_last_sync_at",
    "work_log_last_sync_at",
    "work_log_sync_interval_minutes",
)


def col_exists(cur: pyodbc.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT COL_LENGTH(N'dbo.karta_store_config', ?)",
        name,
    )
    row = cur.fetchone()
    return row is not None and row[0] is not None


def main() -> None:
    sql_path = _ROOT / "sql" / "alter_add_store_sync_timestamps.sql"
    conn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    cur = conn.cursor()
    before = {c: col_exists(cur, c) for c in _COLS}
    print("BEFORE:", before)
    if all(before.values()):
        print("ALREADY_APPLIED")
        return
    raw = sql_path.read_text(encoding="utf-8")
    batches = [b.strip() for b in raw.split("\nGO\n") if b.strip()]
    for i, batch in enumerate(batches, 1):
        if not batch or batch.startswith("/*"):
            continue
        print(f"Batch {i}...")
        cur.execute(batch)
    after = {c: col_exists(cur, c) for c in _COLS}
    print("AFTER:", after)
    if not all(after.values()):
        raise SystemExit("Migration incomplete")
    print("OK")


if __name__ == "__main__":
    main()
