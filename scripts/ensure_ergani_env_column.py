"""Προσθήκη στήλης ergani_env στο karta_store_config."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import cursor  # noqa: E402

DDL = """
IF COL_LENGTH(N'dbo.karta_store_config', N'ergani_env') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
    ADD ergani_env NVARCHAR(16) NOT NULL
        CONSTRAINT DF_karta_store_ergani_env DEFAULT (N'production');
END
"""


def main() -> int:
    with cursor() as cur:
        cur.execute(DDL)
        cur.execute(
            "SELECT COL_LENGTH('dbo.karta_store_config', 'ergani_env') AS col_len"
        )
        ok = cur.fetchone()[0]
    print("ergani_env column:", "OK" if ok else "MISSING")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
