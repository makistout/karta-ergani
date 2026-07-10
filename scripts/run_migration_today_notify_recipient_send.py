"""Εφαρμογή sql/alter_add_today_notify_recipient_send.sql (idempotent)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402


def main() -> int:
    Config.validate_for_startup()
    from app.db import cursor

    sql = (ROOT / "sql" / "alter_add_today_notify_recipient_send.sql").read_text(encoding="utf-8")
    batches = [b.strip() for b in sql.split("GO") if b.strip()]
    with cursor() as cur:
        for batch in batches:
            cur.execute(batch)
    print("OK: karta_today_notify_recipient_send")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
