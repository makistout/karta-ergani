"""Μαζικό backfill πρωτοκόλλων Ergani (WorkCardSearch) ανά κατάστημα."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ergani_env import store_api_context  # noqa: E402
from app.portal_card_protocol_sync import sync_card_protocols_from_portal  # noqa: E402
from app.repo_ergani_protocol import earliest_store_activity_date  # noqa: E402
from app.repo_store import list_store_configs  # noqa: E402

CHUNK_DAYS = 31


def _iso_chunks(from_iso: str, to_iso: str, *, max_days: int = CHUNK_DAYS) -> list[tuple[str, str]]:
    start = datetime.strptime(from_iso[:10], "%Y-%m-%d").date()
    end = datetime.strptime(to_iso[:10], "%Y-%m-%d").date()
    if start > end:
        start, end = end, start
    chunks: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=max_days - 1), end)
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _resolve_from_date(
    store: dict,
    *,
    from_iso: str | None,
) -> date:
    if from_iso:
        return datetime.strptime(from_iso[:10], "%Y-%m-%d").date()
    sid = int(store["id"])
    afm = str(store.get("employer_afm") or "")
    aa = str(store.get("branch_aa") or "0")
    earliest = earliest_store_activity_date(sid, afm, aa)
    if earliest:
        return earliest
    return datetime.today().date() - timedelta(days=365)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill πρωτοκόλλων χτυπημάτων από portal Ergani"
    )
    parser.add_argument("--store-id", type=int, action="append", dest="store_ids")
    parser.add_argument("--from", dest="from_iso", help="Ημερομηνία έναρξης (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_iso", help="Ημερομηνία λήξης (YYYY-MM-DD, default σήμερα)")
    parser.add_argument("--chunk-days", type=int, default=CHUNK_DAYS)
    args = parser.parse_args()

    stores = list_store_configs()
    if args.store_ids:
        wanted = set(args.store_ids)
        stores = [s for s in stores if int(s["id"]) in wanted]
    if not stores:
        print("Δεν βρέθηκαν καταστήματα.")
        return 1

    to_iso = (args.to_iso or datetime.today().strftime("%Y-%m-%d"))[:10]
    fail_count = 0
    ok_count = 0

    for store in stores:
        sid = int(store["id"])
        name = str(store.get("name") or sid)
        start = _resolve_from_date(store, from_iso=args.from_iso)
        from_iso = start.isoformat()
        chunks = _iso_chunks(from_iso, to_iso, max_days=max(1, int(args.chunk_days)))
        ctx = store_api_context(store)
        print(f"\n[{name}] {from_iso} – {to_iso} ({len(chunks)} chunks)", flush=True)
        store_ok = True
        total_rows = 0
        for index, (chunk_from, chunk_to) in enumerate(chunks, start=1):
            print(f"  chunk {index}/{len(chunks)}: {chunk_from} – {chunk_to}…", flush=True)
            started = time.perf_counter()
            result = sync_card_protocols_from_portal(
                ctx,
                from_iso=chunk_from,
                to_iso=chunk_to,
                max_days=args.chunk_days,
            )
            elapsed = time.perf_counter() - started
            if result.get("success"):
                count = int(result.get("count") or 0)
                total_rows += count
                print(
                    f"    OK — {result.get('detail') or count} ({elapsed:.1f}s)",
                    flush=True,
                )
            else:
                store_ok = False
                print(
                    f"    FAIL — {result.get('detail') or 'άγνωστο σφάλμα'} ({elapsed:.1f}s)",
                    flush=True,
                )
        if store_ok:
            ok_count += 1
            print(f"  Σύνολο: {total_rows} πρωτόκολλα", flush=True)
        else:
            fail_count += 1

    print(f"\nΟλοκλήρωση: {ok_count} OK, {fail_count} αποτυχίες")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
