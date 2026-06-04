"""Δημιουργία πίνακα karta_schedule αν λείπει."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402

DDL = """
IF OBJECT_ID(N'dbo.karta_schedule', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_schedule (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_schedule PRIMARY KEY CLUSTERED,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        work_date NVARCHAR(32) NOT NULL,
        employee_afm NVARCHAR(9) NULL,
        hour_from NVARCHAR(16) NULL,
        hour_to NVARCHAR(16) NULL,
        shift_type NVARCHAR(64) NULL,
        break_minutes INT NULL,
        break_in_work INT NULL,
        extra NVARCHAR(500) NULL,
        source_aa NVARCHAR(32) NULL,
        synced_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_schedule_synced DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_karta_schedule_lookup ON dbo.karta_schedule (employer_afm, branch_aa, work_date);
    CREATE INDEX IX_karta_schedule_emp ON dbo.karta_schedule (employee_afm, work_date);
END
"""


def main() -> int:
    cn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    cur = cn.cursor()
    cur.execute(DDL)
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
        ("karta_schedule",),
    )
    ok = int(cur.fetchone()[0])
    cn.close()
    print("karta_schedule exists:", bool(ok))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
