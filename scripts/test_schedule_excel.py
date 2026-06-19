"""Δοκιμή Excel export ψηφιακού ωραρίου (store id=4, 7 ημέρες)."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import repo_store
from app.ergani_env import portal_base_for_env, normalize_ergani_env
from app.portal_schedule_sync import (
    _login_session,
    _open_current_status,
    _portal_base,
    _search_schedule,
)


def main() -> int:
    cfg = repo_store.get_store_config(4)
    if not cfg:
        print("no store")
        return 1
    env = normalize_ergani_env(cfg.get("ergani_env"))
    ctx = {
        "id": cfg["id"],
        "employer_afm": cfg["employer_afm"],
        "branch_aa": cfg.get("branch_aa") or "0",
        "username": cfg["username"],
        "password": cfg["password"],
        "usertype": cfg.get("usertype") or "01",
        "ergani_env": env,
        "portal_base_url": portal_base_for_env(env),
    }
    end = datetime.today()
    start = end - timedelta(days=7)
    date_from = start.strftime("%d/%m/%Y")
    date_to = end.strftime("%d/%m/%Y")

    session = _login_session(ctx)
    portal_base = _portal_base(ctx)
    html, url = _open_current_status(session, portal_base)
    rows, source = _search_schedule(session, html, url, ctx, date_from, date_to)
    print(f"source={source} rows={len(rows)} range={date_from} – {date_to}")
    for r in rows[:5]:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
