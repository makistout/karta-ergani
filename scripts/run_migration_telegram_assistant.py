"""Apply the additive Telegram assistant schema migration."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import cursor  # noqa: E402


def main() -> int:
    sql = (ROOT / "sql" / "alter_add_telegram_assistant.sql").read_text(encoding="utf-8")
    batches = [part.strip() for part in re.split(r"(?im)^\s*GO\s*$", sql) if part.strip()]
    with cursor() as cur:
        for batch in batches:
            cur.execute(batch)
    print("OK: Telegram assistant schema migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
