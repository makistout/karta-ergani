"""Εφαρμογή sql/alter_add_office_users.sql και seed super_admin."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import cursor  # noqa: E402
from app.repo_users import reset_table_cache, seed_roles_permissions, seed_super_admin  # noqa: E402
from config import Config  # noqa: E402


def _split_batches(sql: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?im)^\s*GO\s*$", sql)
        if part.strip()
    ]


def main() -> int:
    sql = (ROOT / "sql" / "alter_add_office_users.sql").read_text(encoding="utf-8")
    with cursor() as cur:
        for batch in _split_batches(sql):
            cur.execute(batch)
    reset_table_cache()
    seed_roles_permissions()
    user, pwd = Config.office_login_credentials()
    seeded_id = seed_super_admin(user, pwd, full_name="Super Admin")
    print(f"OK: office users migration, super_admin_id={seeded_id or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
