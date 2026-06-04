"""Δημιουργία πίνακα karta_work_log αν λείπει."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402

DDL = """
IF OBJECT_ID(N'dbo.karta_work_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_work_log (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_work_log PRIMARY KEY CLUSTERED,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        work_date NVARCHAR(32) NOT NULL,
        employee_afm NVARCHAR(9) NULL,
        hour_from NVARCHAR(16) NULL,
        hour_to NVARCHAR(16) NULL,
        source_aa NVARCHAR(32) NULL,
        is_end_date_different BIT NULL,
        synced_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_work_log_synced DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_karta_work_log_lookup ON dbo.karta_work_log (employer_afm, branch_aa, work_date);
END
"""


def main() -> int:
    cn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    cur = cn.cursor()
    cur.execute(DDL)
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
        ("karta_work_log",),
    )
    ok = int(cur.fetchone()[0])
    cn.close()
    print("karta_work_log exists:", bool(ok))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
