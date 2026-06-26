"""CLI για περιοδικό συγχρονισμό — καλείται από Windows Task Scheduler κάθε 15 λεπτά."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402


def _env_flag(name: str, *, default: bool = True) -> bool:
    import os

    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Συγχρονισμός όλων των καταστημάτων για σήμερα (ωράριο + πραγματική)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Εμφάνιση καταστημάτων χωρίς sync",
    )
    parser.add_argument(
        "--store-id",
        type=int,
        action="append",
        dest="store_ids",
        help="Μόνο συγκεκριμένο κατάστημα (επαναλήψιμο)",
    )
    parser.add_argument(
        "--date",
        dest="work_date",
        help="ISO ημερομηνία (προεπιλογή σήμερα), π.χ. 2026-06-17",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Τρέξε ακόμα κι αν τρέχει ήδη scheduled sync",
    )
    args = parser.parse_args()

    if not _env_flag("KARTA_SCHEDULED_SYNC_ENABLED", default=True):
        print("KARTA_SCHEDULED_SYNC_ENABLED=0 — παράλειψη.")
        return 0

    try:
        Config.validate_for_startup()
    except RuntimeError as ex:
        print(f"ΣΦΑΛΜΑ ρυθμίσεων: {ex}", file=sys.stderr)
        return 1

    from app.scheduled_sync import run_scheduled_sync

    result = run_scheduled_sync(
        store_ids=args.store_ids,
        work_date_iso=args.work_date,
        dry_run=args.dry_run,
        skip_if_running=not args.force,
    )

    if result.get("skipped"):
        print(result.get("reason") or "Παράλειψη — ήδη τρέχει.")
        return 0

    if result.get("dry_run"):
        print(result.get("message") or f"Dry-run: {result.get('count', 0)} καταστήματα")
        for name in result.get("stores") or []:
            print(f"  - {name}")
        return 0

    print(result.get("message") or "Ολοκληρώθηκε.")
    for row in result.get("stores") or []:
        mark = "OK" if row.get("success") else "FAIL"
        print(f"  [{mark}] {row.get('store_name')} — {row.get('detail')}")

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
