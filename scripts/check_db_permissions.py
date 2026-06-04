import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc
from config import Config


def conn_str(db: str) -> str:
    return (
        f"Driver={{{Config.DB_ODBC_DRIVER}}};"
        f"Server={Config.DB_SERVER};Database={db};"
        f"Uid={Config.DB_USERNAME};Pwd={Config.DB_PASSWORD};"
        "TrustServerCertificate=yes;"
    )


for db in ("ergani-karta", "ergani_ii"):
    print(f"\n=== {db} ===")
    try:
        c = pyodbc.connect(conn_str(db), autocommit=True)
        cur = c.cursor()
        cur.execute(
            """
            SELECT r.name FROM sys.database_role_members m
            JOIN sys.database_principals r ON m.role_principal_id = r.principal_id
            JOIN sys.database_principals u ON m.member_principal_id = u.principal_id
            WHERE u.name = USER_NAME()
            """
        )
        print("roles:", [x[0] for x in cur.fetchall()])
        cur.execute(
            """
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE'
            """
        )
        print("dbo tables:", cur.fetchone()[0])
        cur.close()
        c.close()
    except Exception as e:
        print("error:", e)
