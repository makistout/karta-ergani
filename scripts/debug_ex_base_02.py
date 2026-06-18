"""Εμφάνιση raw απάντησης EX_BASE_02 για κατάστημα (χωρίς εκτύπωση passwords)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import repo_store
from app.ergani_client import ErganiClient
from app.ergani_env import base_url_for_env, normalize_ergani_env
from app.ergani_parse import parse_branches
from app.http_helpers import json_or_text

STORE_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 5


def main() -> int:
    cfg = repo_store.get_store_config(STORE_ID)
    if not cfg:
        print(f"Δεν βρέθηκε κατάστημα id={STORE_ID}")
        return 1

    env = normalize_ergani_env(cfg.get("ergani_env"))
    base = base_url_for_env(env)
    web_user = cfg.get("web_username") or ""
    web_pass = cfg.get("web_password") or ""

    print("=== Κατάστημα ===")
    print(f"id={cfg['id']} name={cfg.get('name')} employer_afm={cfg.get('employer_afm')}")
    print(f"web_username={web_user} ergani_env={env}")
    print(f"api_base={base}")
    print()

    client = ErganiClient(base)
    auth = client.authenticate(web_user, web_pass, "02")
    auth_parsed = json_or_text(auth)
    print("=== Authentication ===")
    print(f"HTTP {auth.status_code}")
    if not auth.ok or not isinstance(auth_parsed, dict) or not auth_parsed.get("accessToken"):
        print(json.dumps(auth_parsed, ensure_ascii=False, indent=2))
        return 1
    print("accessToken: OK (κρυμμένο)")
    print()

    token = str(auth_parsed["accessToken"])
    r02 = client.execute_service("EX_BASE_02", [], token)
    parsed = json_or_text(r02)

    print("=== EX_BASE_02 raw response ===")
    print(f"HTTP {r02.status_code}")
    print(json.dumps(parsed, ensure_ascii=False, indent=2))
    print()

    branches = parse_branches(parsed)
    print("=== parse_branches() ===")
    print(json.dumps(branches, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
