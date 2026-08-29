"""Idempotent migration: QR ψηφιακής οργάνωσης ανά σχέση απασχόλησης."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import cursor

SQL_PATH = ROOT / "sql" / "alter_add_employment_work_time_qr.sql"


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    statements = [part.strip() for part in sql.replace("\r\n", "\n").split("\nGO\n") if part.strip()]
    with cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    print("OK: employment work-time QR migration")


if __name__ == "__main__":
    main()
