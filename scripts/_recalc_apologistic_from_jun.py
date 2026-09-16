"""Καθαρό μηδενισμό + επαναϋπολογισμός απολογιστικού από 1/6 έως χθες.

1) Μηδενίζει override/effective/generated για week_from >= 1/6 (όχι approved/locked)
2) Ξαναϋπολογίζει όλα τα καταστήματα με force + discard_overrides
3) Νέα calculation_version από apologistic_snapshot
"""
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
from app.db import cursor  # noqa: E402
from app.repo_store import list_store_configs  # noqa: E402

CUTOFF = date(2026, 6, 1)


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


def wipe_from_june() -> dict[str, int]:
    with cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE d
            SET override_json = NULL,
                override_reason = NULL,
                updated_by = NULL,
                override_updated_at = NULL,
                generated_json = N'{}',
                effective_json = N'{}',
                updated_at = SYSDATETIMEOFFSET()
            FROM dbo.karta_apologistic_day d
            INNER JOIN dbo.karta_apologistic_run r ON r.id = d.run_id
            WHERE r.week_from >= ?
              AND r.status NOT IN (N'approved', N'locked')
            """,
            (CUTOFF,),
        )
        days = int(cur.rowcount or 0)
        cur.execute(
            """
            UPDATE dbo.karta_apologistic_run
            SET generated_report_json = NULL,
                effective_report_json = NULL,
                calculation_version = N'pending-clean',
                error_summary = NULL,
                updated_at = SYSDATETIMEOFFSET()
            WHERE week_from >= ?
              AND status NOT IN (N'approved', N'locked')
            """,
            (CUTOFF,),
        )
        runs = int(cur.rowcount or 0)
    return {"days_wiped": days, "runs_wiped": runs}


def main() -> int:
    start = CUTOFF
    end = date.today() - timedelta(days=1)
    weeks = mondays_from(start, end)
    stores = list_store_configs()

    print(f"calculation_version={CALCULATION_VERSION}")
    print(f"Εύρος: {start.isoformat()} .. {end.isoformat()}")
    print(f"Εβδομάδες ({len(weeks)}): {weeks[0].isoformat()} .. {weeks[-1].isoformat()}")
    print(f"Καταστήματα: {len(stores)}")
    print()

    print("=== ΜΗΔΕΝΙΣΜΟΣ παλιών effective/generated/override ===", flush=True)
    wiped = wipe_from_june()
    print(f"  days_wiped={wiped['days_wiped']} runs_wiped={wiped['runs_wiped']}", flush=True)
    print()

    results: list[dict] = []
    total_start = perf_counter()

    for wi, week_from in enumerate(weeks, 1):
        week_to = week_from + timedelta(days=6)
        print(
            f"=== Εβδομάδα {wi}/{len(weeks)}: {week_from.isoformat()} – {week_to.isoformat()} ===",
            flush=True,
        )
        for si, store in enumerate(stores, 1):
            name = store.get("name") or store.get("id")
            wall_start = perf_counter()
            row = generate_store_week(
                store,
                week_from,
                week_to,
                force=True,
                discard_overrides=True,
            )
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
