"""Portal sync + DB repair για νυχτερινές orphan εξόδους πραγματικής — όλα τα καταστήματα."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402


def main() -> int:
    Config.validate_for_startup()

    days = 30
    if len(sys.argv) > 1:
        try:
            days = max(1, min(int(sys.argv[1]), 90))
        except ValueError:
            print(f"Usage: {Path(__file__).name} [days=1-90]", file=sys.stderr)
            return 2

    from app.date_util import iso_to_ergani_dates
    from app.scheduled_sync import list_syncable_stores, run_work_log_range_sync_for_store
    from app.work_log_overnight import repair_overnight_work_log_for_store

    to_iso = datetime.today().strftime("%Y-%m-%d")
    from_iso = (datetime.today() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    ergani_dates = iso_to_ergani_dates(from_iso, to_iso, days)
    stores = list_syncable_stores()

    print(f"Overnight work-log repair: {from_iso} -> {to_iso} ({days} days)")
    print(f"Stores: {len(stores)}")

    report: list[dict] = []
    total_orphans_before = 0
    total_orphans_after = 0
    sync_ok = 0
    sync_fail = 0

    for cfg in stores:
        sid = int(cfg["id"])
        name = str(cfg.get("name") or sid)
        afm = str(cfg.get("employer_afm") or "")
        aa = str(cfg.get("branch_aa") or "0")
        print(f"\n--- [{sid}] {name} ---", flush=True)

        pre = repair_overnight_work_log_for_store(afm, aa, ergani_dates)
        pre_orphans = pre.get("orphans_before") or []
        pre_changed = pre.get("changed_days") or []
        total_orphans_before += len(pre_orphans)
        if pre_orphans:
            print(f"  PRE-REPAIR DB: {len(pre_orphans)} orphan(s), {len(pre_changed)} day(s) changed", flush=True)
        else:
            print("  PRE-REPAIR DB: no orphans", flush=True)

        sync_out = run_work_log_range_sync_for_store(
            cfg,
            from_iso=from_iso,
            to_iso=to_iso,
            operation="work_log_sync",
        )
        sync_success = bool(sync_out.get("success"))
        if sync_success:
            sync_ok += 1
            wl = sync_out.get("work_log") or {}
            print(
                f"  SYNC OK — {wl.get('count', 0)} records ({wl.get('fetch_source') or wl.get('source')})",
                flush=True,
            )
        else:
            sync_fail += 1
            err = sync_out.get("error") or (sync_out.get("work_log") or {}).get("detail") or "unknown"
            print(f"  SYNC FAIL — {err}", flush=True)

        post = repair_overnight_work_log_for_store(afm, aa, ergani_dates)
        post_orphans = post.get("orphans_after") or []
        post_changed = post.get("changed_days") or []
        total_orphans_after += len(post_orphans)
        if post_changed:
            print(f"  POST-REPAIR DB: {len(post_changed)} day(s) changed", flush=True)
        if post_orphans:
            print(f"  POST-REPAIR DB: {len(post_orphans)} orphan(s) remain", flush=True)
        else:
            print("  POST-REPAIR DB: clean", flush=True)

        report.append({
            "store_id": sid,
            "store_name": name,
            "employer_afm": afm,
            "branch_aa": aa,
            "sync_success": sync_success,
            "orphans_before": pre_orphans,
            "orphans_after": post_orphans,
            "db_changed_days_pre": pre_changed,
            "db_changed_days_post": post_changed,
            "sync": sync_out,
        })

    summary = {
        "from_iso": from_iso,
        "to_iso": to_iso,
        "days": days,
        "stores_total": len(stores),
        "sync_ok": sync_ok,
        "sync_fail": sync_fail,
        "orphans_before_total": total_orphans_before,
        "orphans_after_total": total_orphans_after,
        "stores": report,
    }
    out_path = ROOT / "data" / f"overnight_work_log_repair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\nDone: sync {sync_ok} OK / {sync_fail} FAIL")
    print(f"Orphans: {total_orphans_before} before -> {total_orphans_after} after")
    print(f"Report: {out_path}")
    return 0 if sync_fail == 0 and total_orphans_after == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
