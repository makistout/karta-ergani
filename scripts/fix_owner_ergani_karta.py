import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc
from config import Config

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

c = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
cur = c.cursor()
for sql in (
    "EXEC sp_addrolemember N'db_owner', N'ergani'",
    "ALTER ROLE db_owner ADD MEMBER [ergani]",
):
    try:
        cur.execute(sql)
        print("OK:", sql)
    except pyodbc.Error as e:
        print("FAIL:", sql, "->", e)

cur.execute("SELECT HAS_PERMS_BY_NAME(NULL, NULL, 'CREATE TABLE')")
print("CREATE TABLE perm:", cur.fetchone()[0])

cur.execute(
    """
    SELECT r.name FROM sys.database_role_members m
    JOIN sys.database_principals r ON m.role_principal_id = r.principal_id
    JOIN sys.database_principals u ON m.member_principal_id = u.principal_id
    WHERE u.name = N'ergani'
    """
)
print("roles:", [x[0] for x in cur.fetchall()])

try:
    cur.execute("CREATE TABLE dbo._karta_perm_test (id INT NOT NULL PRIMARY KEY)")
    print("test CREATE TABLE: OK")
    cur.execute("DROP TABLE dbo._karta_perm_test")
except pyodbc.Error as e:
    print("test CREATE TABLE:", e)

cur.close()
c.close()
