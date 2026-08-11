from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402
from config import Config  # noqa: E402


def main() -> int:
    path = ROOT / "sql" / "alter_add_apologistic_snapshots.sql"
    batches = [batch.strip() for batch in path.read_text(encoding="utf-8").split("GO") if batch.strip()]
    conn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    try:
        cur = conn.cursor()
        for index, batch in enumerate(batches, 1):
            cur.execute(batch)
            print(f"OK batch {index}/{len(batches)}")
        cur.close()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
