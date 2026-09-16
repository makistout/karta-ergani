"""Δημιουργία πίνακα karta_specialty_catalog αν λείπει."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repo_specialty_catalog import ENSURE_DDL, TABLE, count_rows, ensure_table  # noqa: E402


def main() -> int:
    ensure_table()
    print(f"{TABLE} ready, rows={count_rows()}")
    # sanity: DDL string exists
    assert "CREATE TABLE" in ENSURE_DDL
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
