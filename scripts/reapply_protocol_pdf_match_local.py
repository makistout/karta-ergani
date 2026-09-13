"""Ξανατρέχει PDF→work_log match από τοπικά PDFs (χωρίς portal).

Παράδειγμα:
  python scripts/reapply_protocol_pdf_match_local.py 2026-08-01
  python scripts/reapply_protocol_pdf_match_local.py 2026-08-01 2026-09-13
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import repo_store
from app.ergani_env import store_api_context
from app.portal_protocol_pdf_match import reapply_local_protocol_pdf_matches_for_range
from app.work_card_payload import tz_athens


def main() -> int:
    args = [a.strip() for a in sys.argv[1:] if a.strip()]
    from_iso = args[0] if args else "2026-08-01"
    to_iso = (
        args[1]
        if len(args) > 1
        else datetime.now(tz_athens()).date().isoformat()
    )
    stores = sorted(repo_store.list_store_configs(), key=lambda s: int(s.get("id") or 0))
    print(f"stores={len(stores)} {from_iso} .. {to_iso}", flush=True)

    report: dict = {
        "from": from_iso,
        "to": to_iso,
        "started_at": datetime.now(tz_athens()).isoformat(),
        "stores": [],
    }
    t0 = time.perf_counter()
    total_updated = 0

    for cfg in stores:
        ctx = store_api_context(cfg)
        sid = int(ctx["id"])
        name = str(ctx.get("name") or sid)
        employer = str(ctx.get("employer_afm") or "")
        branch = str(ctx.get("branch_aa") or "0")
        print(f"\n=== STORE {sid} {name} ===", flush=True)
        t_store = time.perf_counter()
        try:
            summary = reapply_local_protocol_pdf_matches_for_range(
                employer, branch, from_iso, to_iso
            )
        except Exception as ex:
            summary = {
                "success": False,
                "detail": str(ex),
                "match_updated": 0,
            }
            print(f"FAIL {name}: {ex}", flush=True)
        wall = round(time.perf_counter() - t_store, 3)
        upd = int(summary.get("match_updated") or 0)
        total_updated += upd
        row = {
            "store_id": sid,
            "name": name,
            "employer_afm": employer,
            "branch_aa": branch,
            "wall_seconds": wall,
            **{
                k: summary.get(k)
                for k in (
                    "success",
                    "days",
                    "pdfs",
                    "parse_fail",
                    "match_updated",
                    "match_in",
                    "match_out",
                    "match_no_wl",
                    "match_conflict",
                    "match_already_ok",
                    "detail",
                    "day_rows",
                )
            },
        }
        report["stores"].append(row)
        print(
            f"OK {name}: days={summary.get('days')} pdfs={summary.get('pdfs')} "
            f"updated={upd} no_wl={summary.get('match_no_wl')} ({wall}s)",
            flush=True,
        )

    report["finished_at"] = datetime.now(tz_athens()).isoformat()
    report["wall_seconds"] = round(time.perf_counter() - t0, 3)
    report["match_updated_total"] = total_updated
    out = (
        ROOT
        / "data"
        / f"reapply_protocol_pdf_match_{from_iso.replace('-', '')}_{to_iso.replace('-', '')}.json"
    )
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"\nDONE updated={total_updated} wall={report['wall_seconds']}s -> {out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
