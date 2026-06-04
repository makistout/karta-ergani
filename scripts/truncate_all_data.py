"""Διαγραφή όλων των δεδομένων karta_* στη βάση ergani-karta."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402
from app.db import get_connection  # noqa: E402

TABLES = [
    "karta_card_event",
    "karta_declaration",
    "karta_schedule",
    "karta_work_log",
    "karta_employment",
    "karta_parartima",
    "karta_employee",
    "karta_employer",
    "karta_store_config",
]


def main() -> int:
    print(f"Database: {Config.DB_DATABASE} @ {Config.DB_SERVER}")
    conn = get_connection()
    cur = conn.cursor()
    try:
        for tbl in TABLES:
            cur.execute(
                "SELECT OBJECT_ID(?, 'U')",
                (f"dbo.{tbl}",),
            )
            if not cur.fetchone()[0]:
                print(f"  skip (no table): {tbl}")
                continue
            cur.execute(f"DELETE FROM dbo.[{tbl}]")  # noqa: S608 — fixed list
            n = cur.rowcount
            if n < 0:
                cur.execute(f"SELECT COUNT(*) FROM dbo.[{tbl}]")
                n = cur.fetchone()[0]
            print(f"  {tbl}: {n} rows deleted")
        conn.commit()
        print("\nCounts after purge:")
        for tbl in TABLES:
            cur.execute(
                "SELECT OBJECT_ID(?, 'U')",
                (f"dbo.{tbl}",),
            )
            if not cur.fetchone()[0]:
                continue
            cur.execute(f"SELECT COUNT(*) FROM dbo.[{tbl}]")
            print(f"  {tbl}: {cur.fetchone()[0]}")
        print("\nOK — η βάση είναι κενή. Ξεκινήστε από wizard καταστήματος στο UI.")
        return 0
    except Exception as ex:
        conn.rollback()
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
