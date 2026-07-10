"""One-off 90-day work log repair sync for all syncable stores."""

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

    from app.scheduled_sync import list_syncable_stores, run_work_log_range_sync_for_store

    days = 90
    to_iso = datetime.today().strftime("%Y-%m-%d")
    from_iso = (datetime.today() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    stores = list_syncable_stores()

    print(f"90-day work log repair: {from_iso} -> {to_iso}")
    print(f"Stores: {len(stores)}")

    results: list[dict] = []
    ok_count = 0
    fail_count = 0

    for cfg in stores:
        sid = int(cfg["id"])
        name = str(cfg.get("name") or sid)
        print(f"\n--- [{sid}] {name} ---", flush=True)
        out = run_work_log_range_sync_for_store(
            cfg,
            from_iso=from_iso,
            to_iso=to_iso,
            operation="work_log_sync",
        )
        success = bool(out.get("success"))
        if success:
            ok_count += 1
            wl = out.get("work_log") or {}
            print(
                f"OK — {wl.get('count', 0)} records, source={wl.get('fetch_source') or wl.get('source')}",
                flush=True,
            )
        else:
            fail_count += 1
            err = out.get("error") or (out.get("work_log") or {}).get("detail") or "unknown"
            print(f"FAIL — {err}", flush=True)
        results.append(
            {
                "store_id": sid,
                "store_name": name,
                "success": success,
                "from_iso": from_iso,
                "to_iso": to_iso,
                "result": out,
            }
        )

    summary = {
        "from_iso": from_iso,
        "to_iso": to_iso,
        "days": days,
        "stores_total": len(stores),
        "ok": ok_count,
        "fail": fail_count,
        "results": results,
    }
    out_path = ROOT / "data" / f"manual_90day_repair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"\nDone: {ok_count} OK, {fail_count} FAIL")
    print(f"Summary: {out_path}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
