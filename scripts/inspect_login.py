import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc
from config import Config

cs = Config.pyodbc_connection_string()
c = pyodbc.connect(cs, autocommit=True)
cur = c.cursor()
cur.execute("SELECT SUSER_SNAME(), USER_NAME(), ORIGINAL_LOGIN()")
print("login row:", cur.fetchone())
cur.execute(
    "SELECT name, type_desc FROM sys.database_principals WHERE type IN ('S','U','G') ORDER BY name"
)
print("principals:")
for r in cur.fetchall():
    print(" ", r)
cur.execute(
    """
    SELECT dp.name, r.name AS role_name
    FROM sys.database_role_members rm
    JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
    JOIN sys.database_principals dp ON rm.member_principal_id = dp.principal_id
    WHERE dp.name = N'ergani'
    """
)
print("ergani roles:", cur.fetchall())
cur.execute("SELECT HAS_PERMS_BY_NAME(NULL, NULL, 'CREATE TABLE')")
print("CREATE TABLE perm:", cur.fetchone()[0])
cur.close()
c.close()
