"""Idempotent migration: auto_close_fixed_exit_time."""

from __future__ import annotations

from pathlib import Path

from app.db import cursor

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "alter_add_auto_close_fixed_exit_time.sql"


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    batches = [b.strip() for b in sql.split("\nGO") if b.strip() and not b.strip().startswith("/*")]
    # Simple: run whole file without GO handling via pyodbc batches
    statements = []
    buf: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            chunk = "\n".join(buf).strip()
            if chunk:
                statements.append(chunk)
            buf = []
        else:
            buf.append(line)
    chunk = "\n".join(buf).strip()
    if chunk:
        statements.append(chunk)
    with cursor() as cur:
        for stmt in statements:
            cur.execute(stmt)
    print("OK: auto_close_fixed_exit_time migration")


if __name__ == "__main__":
    main()
