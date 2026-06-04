"""Προσπάθεια χορήγησης db_owner στον SQL login ergani στη βάση ergani-karta."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc
from config import Config


def cs(db: str) -> str:
    return (
        f"Driver={{{Config.DB_ODBC_DRIVER}}};"
        f"Server={Config.DB_SERVER};Database={db};"
        f"Uid={Config.DB_USERNAME};Pwd={Config.DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    steps = [
        ("master", "USE [ergani-karta]"),
        ("master", "IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'ergani') CREATE USER [ergani] FOR LOGIN [ergani]"),
        ("master", "USE [ergani-karta]"),
        ("master", "EXEC sp_addrolemember N'db_owner', N'ergani'"),
        ("ergani-karta", "GRANT CREATE TABLE TO [ergani]"),
        ("ergani-karta", "GRANT ALTER ON SCHEMA::dbo TO [ergani]"),
    ]
    for db, sql in steps:
        try:
            c = pyodbc.connect(cs(db), autocommit=True)
            cur = c.cursor()
            cur.execute(sql)
            print(f"OK [{db}]: {sql[:60]}...")
            cur.close()
            c.close()
        except pyodbc.Error as e:
            print(f"FAIL [{db}]: {sql[:60]}... -> {e}")

    c = pyodbc.connect(cs("ergani-karta"), autocommit=True)
    cur = c.cursor()
    cur.execute("SELECT HAS_PERMS_BY_NAME(NULL, NULL, 'CREATE TABLE')")
    print("CREATE TABLE perm after grants:", cur.fetchone()[0])
    cur.close()
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
