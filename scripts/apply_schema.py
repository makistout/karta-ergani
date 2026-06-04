"""Εφαρμογή sql/schema.sql στη βάση ergani-karta (pyodbc)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402


def main() -> int:
    schema_path = ROOT / "sql" / "schema.sql"
    if not schema_path.is_file():
        print(f"Δεν βρέθηκε: {schema_path}", file=sys.stderr)
        return 1
    raw = schema_path.read_text(encoding="utf-8")
    batches = [b.strip() for b in raw.split("GO") if b.strip()]
    conn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    cur = conn.cursor()
    try:
        for i, batch in enumerate(batches, 1):
            cur.execute(batch)
            print(f"OK batch {i}/{len(batches)}")
    finally:
        cur.close()
        conn.close()
    print(f"Ολοκληρώθηκε — {Config.DB_SERVER} / {Config.DB_DATABASE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
