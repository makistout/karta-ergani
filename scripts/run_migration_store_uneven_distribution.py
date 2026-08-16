"""Idempotent migration: per-store uneven-distribution preference."""

from __future__ import annotations

from pathlib import Path

from app.db import cursor

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "alter_add_store_uneven_distribution.sql"


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
    print("OK: uneven_distribution_enabled migration")


if __name__ == "__main__":
    main()
