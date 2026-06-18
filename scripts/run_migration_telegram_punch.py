"""Εφαρμογή sql/alter_add_notify_pin_and_punch_token.sql"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc
from config import Config

sql = (ROOT / "sql" / "alter_add_notify_pin_and_punch_token.sql").read_text(encoding="utf-8")
batches = [b.strip() for b in sql.split("GO") if b.strip()]
conn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
cur = conn.cursor()
for i, batch in enumerate(batches, 1):
    cur.execute(batch)
    print(f"OK batch {i}/{len(batches)}")
cur.close()
conn.close()
print("Ολοκληρώθηκε.")
