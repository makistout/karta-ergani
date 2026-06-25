"""Εφαρμογή sql/alter_add_notify_recipient_policy.sql"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import cursor  # noqa: E402


def _split_batches(sql: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?im)^\s*GO\s*$", sql)
        if part.strip()
    ]


def main() -> int:
    sql = (ROOT / "sql" / "alter_add_notify_recipient_policy.sql").read_text(
        encoding="utf-8"
    )
    with cursor() as cur:
        for batch in _split_batches(sql):
            cur.execute(batch)
    print("OK: notify recipient policy migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
