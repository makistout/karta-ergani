from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.apologistic_snapshot import generate_previous_week, generate_store_week  # noqa: E402
from app.repo_store import list_store_configs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Αποθήκευση απολογιστικού για όλα τα καταστήματα")
    parser.add_argument("--from", dest="week_from")
    args = parser.parse_args()
    stores = list_store_configs()
    if args.week_from:
        start = datetime.strptime(args.week_from, "%Y-%m-%d").date()
        end = start + timedelta(days=6)
        rows = []
        for index, store in enumerate(stores, 1):
            print(f"[{index}/{len(stores)}] {store.get('name')}...", flush=True)
            row = generate_store_week(store, start, end)
            rows.append(row)
            print(f"  {'OK' if row.get('success') else 'FAIL'} — {row.get('days', row.get('error', ''))}", flush=True)
        result = {"from": start.isoformat(), "to": end.isoformat(), "stores": rows}
        result["ok_count"] = sum(bool(row.get("success")) for row in result["stores"])
        result["fail_count"] = len(result["stores"]) - result["ok_count"]
    else:
        result = generate_previous_week(stores)
    print(f"Απολογιστικό {result['from']} – {result['to']}: {result['ok_count']} OK, {result['fail_count']} αποτυχίες")
    for row in result["stores"]:
        mark = "OK" if row.get("success") else "FAIL"
        print(f"  [{mark}] {row.get('store_name')} — {row.get('days', row.get('error', ''))}")
    return 0 if result["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
