"""Εφαρμογή sql/alter_add_store_notify_recipients.sql"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pyodbc
from config import Config

sql = (ROOT / "sql" / "alter_add_store_notify_recipients.sql").read_text(encoding="utf-8")
batches = [b.strip() for b in sql.split("GO") if b.strip()]
conn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
cur = conn.cursor()
for i, batch in enumerate(batches, 1):
    cur.execute(batch)
    print(f"OK batch {i}/{len(batches)}")
cur.execute(
    "SELECT COUNT(1) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = N'karta_store_notify_recipient'"
)
print("table exists:", cur.fetchone()[0])
cur.close()
conn.close()
