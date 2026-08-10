"""Apply the additive card-listener schema migration."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pyodbc  # noqa: E402

from config import Config  # noqa: E402


def main() -> int:
    path = ROOT / "sql" / "alter_add_card_listener.sql"
    batches = [part.strip() for part in path.read_text(encoding="utf-8").split("GO") if part.strip()]
    with pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True) as conn:
        cur = conn.cursor()
        for batch in batches:
            cur.execute(batch)
        cur.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dbo.karta_store_config),
                (SELECT COUNT(*) FROM dbo.karta_store_config WHERE card_submission_mode = N'erganios'),
                OBJECT_ID(N'dbo.karta_card_listener_device', N'U'),
                OBJECT_ID(N'dbo.karta_card_listener_job', N'U'),
                OBJECT_ID(N'dbo.karta_card_listener_attempt', N'U')
            """
        )
        total, direct, device_obj, job_obj, attempt_obj = cur.fetchone()
    if total != direct or not all((device_obj, job_obj, attempt_obj)):
        print("Migration verification failed.", file=sys.stderr)
        return 2
    print(f"Card-listener schema migration applied. Stores unchanged: {direct}/{total} use erganios.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
