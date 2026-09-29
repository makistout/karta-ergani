"""Idempotent migration: store AME + employee AMKA/ΑΜΑ for APD preview."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import cursor  # noqa: E402

SQL_PATH = ROOT / "sql" / "alter_add_apd_identity.sql"


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            statement = "\n".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
        else:
            buffer.append(line)
    statement = "\n".join(buffer).strip()
    if statement:
        statements.append(statement)

    with cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    print("OK: APD identity (ame / amka / amika)")


if __name__ == "__main__":
    main()
