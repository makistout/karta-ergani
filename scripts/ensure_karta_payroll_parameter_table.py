"""Δημιουργία πίνακα karta_payroll_parameter και seed εταιρικών συντελεστών."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402

DDL = (ROOT / "sql" / "alter_add_karta_payroll_parameter.sql").read_text(encoding="utf-8")
# pyodbc δεν τρέχει παρτίδες GO.
DDL = "\n".join(line for line in DDL.splitlines() if line.strip().upper() != "GO")


def main() -> int:
    cn = pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True)
    cur = cn.cursor()
    cur.execute(DDL)
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
        ("karta_payroll_parameter",),
    )
    ok = int(cur.fetchone()[0])
    cn.close()
    if not ok:
        print("karta_payroll_parameter exists: False")
        return 1
    from app.repo_payroll import ensure_seeded, tables_available

    if not tables_available():
        print("karta_payroll_parameter exists: False")
        return 1
    ensure_seeded()
    print("karta_payroll_parameter exists: True")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
