"""Add and verify actual Ergani submission network identity columns."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pyodbc  # noqa: E402
from config import Config  # noqa: E402

def main() -> int:
    raw = (ROOT / "sql" / "alter_add_submission_network_identity.sql").read_text(encoding="utf-8")
    with pyodbc.connect(Config.pyodbc_connection_string(), autocommit=True) as conn:
        cur = conn.cursor()
        for batch in (x.strip() for x in raw.split("GO") if x.strip()): cur.execute(batch)
        cur.execute("SELECT COL_LENGTH(N'dbo.karta_declaration', N'submission_ip'), COL_LENGTH(N'dbo.karta_declaration', N'submission_channel'), COL_LENGTH(N'dbo.karta_declaration', N'executor_instance'), COL_LENGTH(N'dbo.karta_card_listener_device', N'last_seen_ip'), COL_LENGTH(N'dbo.karta_card_listener_job', N'submission_ip'), COL_LENGTH(N'dbo.karta_card_listener_attempt', N'submission_ip')")
        if not all(cur.fetchone()): return 2
    print("Submission network identity migration applied.")
    return 0

if __name__ == "__main__": raise SystemExit(main())
