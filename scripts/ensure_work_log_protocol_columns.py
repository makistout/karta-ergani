"""Προσθήκη protocol_from / protocol_to στο karta_work_log αν λείπουν."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402

DDL = """
IF COL_LENGTH(N'dbo.karta_work_log', N'protocol_from') IS NULL
    ALTER TABLE dbo.karta_work_log ADD protocol_from NVARCHAR(128) NULL;

IF COL_LENGTH(N'dbo.karta_work_log', N'protocol_to') IS NULL
    ALTER TABLE dbo.karta_work_log ADD protocol_to NVARCHAR(128) NULL;
"""


def main() -> int:
    cn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    cur = cn.cursor()
    cur.execute(DDL)
    cur.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = N'karta_work_log'
          AND COLUMN_NAME IN (N'protocol_from', N'protocol_to')
        """
    )
    n = int(cur.fetchone()[0])
    cn.close()
    print("karta_work_log protocol columns:", n, "/ 2")
    return 0 if n == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
