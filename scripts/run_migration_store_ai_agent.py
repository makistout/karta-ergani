"""Idempotent migration: per-store AI Agent subscription flag."""

from __future__ import annotations

from pathlib import Path

from app.db import cursor

SQL_PATH = Path(__file__).resolve().parents[1] / "sql" / "alter_add_store_ai_agent.sql"


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    statements = [part.strip() for part in sql.replace("\r\n", "\n").split("\nGO\n") if part.strip()]
    with cursor() as cur:
        for statement in statements:
            cur.execute(statement)
    print("OK: ai_agent_enabled migration")


if __name__ == "__main__":
    main()
