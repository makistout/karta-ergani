"""Probe EX_BASE_04 with store credentials; save sample if successful."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

from app import repo_store as repo  # noqa: E402
from app.ergani_env import api_login_credentials, client_for_store, store_api_context  # noqa: E402


def try_call(label: str, client, user: str, pwd: str, ut: str, year: int, month: int) -> dict:
    auth = client.authenticate(user, pwd, ut)
    if not auth.ok:
        return {
            "label": label,
            "error": "auth failed",
            "status": auth.status_code,
            "body": auth.text[:300],
        }
    token = auth.json().get("accessToken")
    params = [
        {"ParameterName": "ReportYear", "ParameterValue": str(year)},
        {"ParameterName": "ReportMonth", "ParameterValue": str(month)},
    ]
    resp = client.execute_service("EX_BASE_04", params, token)
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:500]
    return {
        "label": label,
        "status": resp.status_code,
        "year": year,
        "month": month,
        "body": body,
    }


def main() -> None:
    stores = repo.list_store_configs() or []
    now = datetime.now()
    months = [(now.year, now.month)]
    if now.month > 1:
        months.append((now.year, now.month - 1))
    else:
        months.append((now.year - 1, 12))

    attempts: list[dict] = []
    for s in stores:
        cfg = repo.get_store_config(s["id"])
        if not cfg:
            continue
        ctx = store_api_context(cfg)
        client = client_for_store(cfg)
        user, pwd, ut = api_login_credentials(ctx)
        if not user or not pwd:
            continue
        for year, month in months:
            attempts.append(
                try_call(f"store {cfg['name']}", client, user, pwd, ut, year, month)
            )

    out_attempts = ROOT / "documentation" / "ex_base_04_live_attempts.json"
    out_attempts.write_text(
        json.dumps(attempts, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for a in attempts:
        print(a["label"], a.get("status"), a.get("year"), a.get("month"))
        if a.get("status") == 200:
            body = a["body"]
            ex = body.get("EX_BASE_04") if isinstance(body, dict) else None
            mk = ex.get("MiniaiaKatastash") if isinstance(ex, dict) else None
            if isinstance(mk, dict):
                mk = [mk]
            n = len(mk) if isinstance(mk, list) else 0
            print("  records", n)
            sample = ROOT / "documentation" / "ex_base_04_sample_response.json"
            sample.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
            print("  saved", sample)
            if n and isinstance(mk[0], dict):
                print("  first keys", list(mk[0].keys())[:12])
            return
        if isinstance(a.get("body"), dict):
            print(" ", (a["body"].get("message") or "")[:120])

    print("No successful EX_BASE_04 response; see", out_attempts)


if __name__ == "__main__":
    main()
