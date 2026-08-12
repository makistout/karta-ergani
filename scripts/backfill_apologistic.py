from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.apologistic_snapshot import generate_previous_week, generate_store_week  # noqa: E402
from app.repo_store import list_store_configs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Αποθήκευση απολογιστικού για όλα τα καταστήματα")
    parser.add_argument("--from", dest="week_from")
    parser.add_argument("--to", dest="week_to", help="Τελευταία ημερομηνία εύρους (τρέχουν μόνο πλήρεις εβδομάδες)")
    parser.add_argument("--timing-json", dest="timing_json", help="Αρχείο JSON με αναλυτικούς χρόνους ανά εβδομάδα/κατάστημα")
    parser.add_argument("--store-id", type=int, action="append", dest="store_ids")
    args = parser.parse_args()
    stores = list_store_configs()
    if args.store_ids:
        wanted = set(args.store_ids)
        stores = [store for store in stores if int(store["id"]) in wanted]
    if args.week_from:
        start = datetime.strptime(args.week_from, "%Y-%m-%d").date()
        range_to = datetime.strptime(args.week_to, "%Y-%m-%d").date() if args.week_to else start + timedelta(days=6)
        week_starts = []
        cursor_start = start
        while cursor_start + timedelta(days=6) <= range_to:
            week_starts.append(cursor_start)
            cursor_start += timedelta(days=7)
        rows = []
        total_jobs = len(week_starts) * len(stores)
        for week_index, current_start in enumerate(week_starts):
            current_end = current_start + timedelta(days=6)
            for store_index, store in enumerate(stores, 1):
                job_index = week_index * len(stores) + store_index
                print(
                    f"[{job_index}/{total_jobs}] {current_start} – {current_end} · {store.get('name')}...",
                    flush=True,
                )
                started = time.perf_counter()
                row = generate_store_week(store, current_start, current_end)
                row["week_from"] = current_start.isoformat()
                row["week_to"] = current_end.isoformat()
                row["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                rows.append(row)
                if args.timing_json:
                    Path(args.timing_json).write_text(
                        json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
                    )
                print(
                    f"  {'OK' if row.get('success') else 'FAIL'} — "
                    f"{row.get('days', row.get('error', ''))} — {row['elapsed_seconds']:.3f}s",
                    flush=True,
                )
        final_to = week_starts[-1] + timedelta(days=6) if week_starts else start
        result = {"from": start.isoformat(), "to": final_to.isoformat(), "stores": rows}
        result["ok_count"] = sum(bool(row.get("success")) for row in result["stores"])
        result["fail_count"] = len(result["stores"]) - result["ok_count"]
    else:
        result = generate_previous_week(stores)
    print(f"Απολογιστικό {result['from']} – {result['to']}: {result['ok_count']} OK, {result['fail_count']} αποτυχίες")
    for row in result["stores"]:
        mark = "OK" if row.get("success") else "FAIL"
        elapsed = f" — {row['elapsed_seconds']:.3f}s" if row.get("elapsed_seconds") is not None else ""
        print(f"  [{mark}] {row.get('store_name')} — {row.get('days', row.get('error', ''))}{elapsed}")
    return 0 if result["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
