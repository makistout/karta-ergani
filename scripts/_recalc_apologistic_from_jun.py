"""Επαναϋπολογισμός απολογιστικού από 1/6/2026 — χρόνοι ανά κατάστημα/εβδομάδα."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.apologistic_snapshot import CALCULATION_VERSION, generate_store_week  # noqa: E402
from app.repo_store import list_store_configs  # noqa: E402


def mondays_from(start: date, end: date) -> list[date]:
    first = start - timedelta(days=start.weekday())
    last = end - timedelta(days=end.weekday())
    weeks: list[date] = []
    day = first
    while day <= last:
        if day + timedelta(days=6) >= start:
            weeks.append(day)
        day += timedelta(days=7)
    return weeks


def main() -> int:
    start = date(2026, 6, 1)
    end = date.today() - timedelta(days=1)
    weeks = mondays_from(start, end)
    stores = list_store_configs()

    print(f"calculation_version={CALCULATION_VERSION}")
    print(f"Εβδομάδες ({len(weeks)}): {weeks[0].isoformat()} .. {weeks[-1].isoformat()}")
    print(f"Καταστήματα: {len(stores)}")
    print()

    results: list[dict] = []
    total_start = perf_counter()

    for wi, week_from in enumerate(weeks, 1):
        week_to = week_from + timedelta(days=6)
        print(f"=== Εβδομάδα {wi}/{len(weeks)}: {week_from.isoformat()} – {week_to.isoformat()} ===", flush=True)
        for si, store in enumerate(stores, 1):
            name = store.get("name") or store.get("id")
            wall_start = perf_counter()
            row = generate_store_week(store, week_from, week_to)
            wall = perf_counter() - wall_start
            results.append(row)
            if row.get("success") and not row.get("skipped"):
                status = "OK"
            elif row.get("skipped"):
                status = f"SKIP ({row.get('reason', '')})"
            else:
                status = f"FAIL ({row.get('error', '')})"
            print(
                f"  [{si}/{len(stores)}] {name}: "
                f"{row.get('elapsed_seconds', 0):.3f}s (wall {wall:.3f}s) "
                f"days={row.get('days', '—')} {status}",
                flush=True,
            )

    total_elapsed = round(perf_counter() - total_start, 3)

    print()
    print("=" * 90)
    print("ΠΙΝΑΚΑΣ ΑΝΑ ΚΑΤΑΣΤΗΜΑ / ΕΒΔΟΜΑΔΑ")
    print("=" * 90)
    print(f"{'Κατάστημα':<28} {'Εβδομάδα':<26} {'Χρόνος':>9} {'Ημέρες':>7} {'Κατάσταση'}")
    print("-" * 90)
    for row in results:
        name = str(row.get("store_name") or row.get("store_id") or "?")[:27]
        week_label = f"{row['week_from']} – {row['week_to']}"
        elapsed = f"{row.get('elapsed_seconds', 0):.3f}s"
        days = str(row.get("days", "—"))
        if row.get("success") and not row.get("skipped"):
            status = "OK"
        elif row.get("skipped"):
            status = "SKIP"
        else:
            status = "FAIL"
        print(f"{name:<28} {week_label:<26} {elapsed:>9} {days:>7} {status}")

    print()
    print("ΣΥΝΟΨΗ ΑΝΑ ΚΑΤΑΣΤΗΜΑ")
    print("-" * 60)
    by_store: dict[str, dict] = {}
    for row in results:
        key = str(row.get("store_name") or row.get("store_id"))
        bucket = by_store.setdefault(key, {"ok": 0, "skip": 0, "fail": 0, "sec": 0.0, "weeks": 0})
        bucket["weeks"] += 1
        bucket["sec"] += float(row.get("elapsed_seconds") or 0)
        if row.get("success") and not row.get("skipped"):
            bucket["ok"] += 1
        elif row.get("skipped"):
            bucket["skip"] += 1
        else:
            bucket["fail"] += 1
    for name in sorted(by_store):
        bucket = by_store[name]
        print(
            f"{name:<28} εβδομάδες={bucket['weeks']} "
            f"OK={bucket['ok']} SKIP={bucket['skip']} FAIL={bucket['fail']} "
            f"χρόνος={bucket['sec']:.2f}s"
        )

    print()
    print("ΣΥΝΟΨΗ ΑΝΑ ΕΒΔΟΜΑΔΑ")
    print("-" * 60)
    by_week: dict[str, dict] = {}
    for row in results:
        key = str(row["week_from"])
        bucket = by_week.setdefault(key, {"ok": 0, "skip": 0, "fail": 0, "sec": 0.0, "stores": 0})
        bucket["stores"] += 1
        bucket["sec"] += float(row.get("elapsed_seconds") or 0)
        if row.get("success") and not row.get("skipped"):
            bucket["ok"] += 1
        elif row.get("skipped"):
            bucket["skip"] += 1
        else:
            bucket["fail"] += 1
    for week_from in sorted(by_week):
        bucket = by_week[week_from]
        week_to = (date.fromisoformat(week_from) + timedelta(days=6)).isoformat()
        print(
            f"{week_from} – {week_to}: καταστήματα={bucket['stores']} "
            f"OK={bucket['ok']} SKIP={bucket['skip']} FAIL={bucket['fail']} "
            f"χρόνος={bucket['sec']:.2f}s"
        )

    ok = sum(1 for row in results if row.get("success") and not row.get("skipped"))
    skip = sum(1 for row in results if row.get("skipped"))
    fail = sum(1 for row in results if not row.get("success"))
    print()
    print(
        f"ΤΕΛΙΚΟ ΣΥΝΟΛΟ: runs={len(results)} OK={ok} SKIP={skip} FAIL={fail} "
        f"συνολικός_χρόνος={total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)"
    )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
