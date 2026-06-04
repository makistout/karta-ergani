"""Δημιουργία βάσης ergani-karta (αν λείπει) + εφαρμογή sql/schema.sql."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402


def _conn_str(database: str) -> str:
    d = Config.DB_ODBC_DRIVER
    return (
        f"Driver={{{d}}};"
        f"Server={Config.DB_SERVER};"
        f"Database={database};"
        f"Uid={Config.DB_USERNAME};"
        f"Pwd={Config.DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )


def ensure_database() -> None:
    db = Config.DB_DATABASE
    safe_name = db.replace("]", "]]")
    conn = pyodbc.connect(_conn_str("master"), autocommit=True)
    cur = conn.cursor()
    try:
        cur.execute("SELECT DB_ID(?)", (db,))
        if cur.fetchone()[0] is not None:
            print(f"Η βάση [{db}] υπάρχει ήδη.")
            return
        print(f"Δημιουργία βάσης [{db}]...")
        cur.execute(f"CREATE DATABASE [{safe_name}]")
        print("OK — CREATE DATABASE")
    finally:
        cur.close()
        conn.close()


def apply_schema() -> None:
    schema_path = ROOT / "sql" / "schema.sql"
    raw = schema_path.read_text(encoding="utf-8")
    batches = [b.strip() for b in re.split(r"^\s*GO\s*$", raw, flags=re.MULTILINE | re.IGNORECASE) if b.strip()]
    conn = pyodbc.connect(_conn_str(Config.DB_DATABASE), autocommit=True)
    cur = conn.cursor()
    try:
        for i, batch in enumerate(batches, 1):
            cur.execute(batch)
            print(f"OK schema batch {i}/{len(batches)}")
    finally:
        cur.close()
        conn.close()


def list_tables() -> list[str]:
    conn = pyodbc.connect(_conn_str(Config.DB_DATABASE), autocommit=True)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print(f"Server: {Config.DB_SERVER}")
    print(f"Database: {Config.DB_DATABASE}")
    print(f"User: {Config.DB_USERNAME}")
    try:
        ensure_database()
        apply_schema()
        tables = list_tables()
        print(f"\nΠίνακες dbo ({len(tables)}):")
        for t in tables:
            print(f"  - {t}")
        print("\nΟλοκληρώθηκε επιτυχώς.")
        return 0
    except pyodbc.Error as ex:
        print(f"\nΣΦΑΛΜΑ SQL: {ex}", file=sys.stderr)
        print(
            "\nΑν βλέπεις 'permission denied': ζητήστε από DBA "
            "CREATE DATABASE / db_owner στο ergani-karta για τον login ergani.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
