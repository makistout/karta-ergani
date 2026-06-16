"""Verify EX_BASE_04 API call vs ServicesList and working EX_BASE_01."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)

from app import repo_store as repo  # noqa: E402
from app.ergani_client import ErganiClient  # noqa: E402
from app.ergani_env import api_login_credentials, client_for_store, store_api_context  # noqa: E402


def main() -> None:
    stores = repo.list_store_configs() or []
    if not stores:
        print("No stores")
        return
    cfg = repo.get_store_config(stores[0]["id"])
    if not cfg:
        print("No store config")
        return
    ctx = store_api_context(cfg)
    client = client_for_store(cfg)
    user, pwd, ut = api_login_credentials(ctx)
    print("store:", cfg["name"])
    print("api_base:", ctx["api_base_url"])
    print("api_user:", user, "usertype:", ut)

    auth = client.authenticate(user, pwd, ut)
    print("auth:", auth.status_code)
    if not auth.ok:
        print(auth.text[:300])
        return
    token = auth.json().get("accessToken")

    r01 = client.execute_service("EX_BASE_01", [], token)
    print("EX_BASE_01:", r01.status_code)

    sl = client.services_list(token)
    print("ServicesList:", sl.status_code)
    out = ROOT / "documentation" / "ex_base_04_api_verify.json"
    result: dict = {"store": cfg["name"], "checks": []}

    if sl.ok:
        data = sl.json()
        services = data if isinstance(data, list) else data.get("data") or data
        base04 = None
        if isinstance(services, list):
            for s in services:
                code = (s.get("code") or s.get("Code") or s.get("serviceCode") or "").upper()
                if code == "EX_BASE_04":
                    base04 = s
                    break
        result["ex_base_04_in_services_list"] = base04 is not None
        result["ex_base_04_service_meta"] = base04
        if base04:
            print("EX_BASE_04 found in ServicesList")
            print(json.dumps(base04, ensure_ascii=False, indent=2)[:2000])
        else:
            print("EX_BASE_04 NOT in ServicesList")
            codes = []
            if isinstance(services, list):
                for s in services[:30]:
                    codes.append(s.get("code") or s.get("Code") or s.get("serviceCode"))
            result["sample_service_codes"] = codes

    attempts = [
        ("pdf_exact", [
            {"ParameterName": "ReportYear", "ParameterValue": "2024"},
            {"ParameterName": "ReportMonth", "ParameterValue": "10"},
        ]),
        ("month_padded", [
            {"ParameterName": "ReportYear", "ParameterValue": "2024"},
            {"ParameterName": "ReportMonth", "ParameterValue": "10"},
        ]),
        ("month_no_pad", [
            {"ParameterName": "ReportYear", "ParameterValue": "2024"},
            {"ParameterName": "ReportMonth", "ParameterValue": "10"},
        ]),
        ("reversed_order", [
            {"ParameterName": "ReportMonth", "ParameterValue": "10"},
            {"ParameterName": "ReportYear", "ParameterValue": "2024"},
        ]),
        ("recent_2025_05", [
            {"ParameterName": "ReportYear", "ParameterValue": "2025"},
            {"ParameterName": "ReportMonth", "ParameterValue": "5"},
        ]),
    ]
    for label, params in attempts:
        body = {"ServiceCode": "EX_BASE_04", "Parameters": params}
        resp = client.execute_service("EX_BASE_04", params, token)
        try:
            parsed = resp.json()
        except Exception:
            parsed = resp.text[:500]
        entry = {
            "label": label,
            "request": body,
            "status": resp.status_code,
            "response": parsed,
        }
        result["checks"].append(entry)
        msg = parsed.get("message") if isinstance(parsed, dict) else ""
        print(f"  {label}: HTTP {resp.status_code} — {msg or 'OK'}")

    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", out)


if __name__ == "__main__":
    main()
