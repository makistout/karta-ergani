from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402


def main() -> int:
    path = ROOT / "sql" / "alter_add_store_action_settings.sql"
    raw = path.read_text(encoding="utf-8")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
