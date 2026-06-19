"""Εφαρμογή sql/alter_add_notify_pin_plain.sql (idempotent)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc
from config import Config

sql_path = ROOT / "sql" / "alter_add_notify_pin_plain.sql"
sql = sql_path.read_text(encoding="utf-8")
batches = [b.strip() for b in sql.split("GO") if b.strip()]
conn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
cur = conn.cursor()
for i, batch in enumerate(batches, 1):
    cur.execute(batch)
    print(f"OK batch {i}/{len(batches)}")
cur.execute(
    "SELECT COL_LENGTH(N'dbo.karta_store_notify_recipient', N'notify_pin')"
)
row = cur.fetchone()
print("OK: notify_pin column exists" if row and row[0] is not None else "MISSING: notify_pin")
cur.close()
conn.close()
