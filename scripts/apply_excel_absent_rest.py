"""Εφαρμογή ΡΕΠΟ για εργαζόμενους που λείπουν από τα φύλλα Excel (import_action=absent)."""

from __future__ import annotations

import sys
from pathlib import Path

from app import create_app
from app.ergani_env import store_api_context
from app.http_helpers import ensure_ergani_bearer
from app.repo_store import get_store_config
from app.schedule_excel_import import parse_weekly_schedule_workbook
from app.schedule_import_service import _sync_schedule_after_import, apply_import_row
from app.audit_log import record_audit_event
from app.today_notify_logic import ergani_date_to_iso

STORE_ID = 6
EXCEL_PATH = Path(r"C:\Users\Administrator\Downloads\weekly_schedule_template_stanotas_mykonos (1).xlsx")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if not EXCEL_PATH.is_file():
        print("ERROR: Δεν βρέθηκε το Excel:", EXCEL_PATH)
        return 1

    cfg = get_store_config(STORE_ID)
    if not cfg:
        print("ERROR: Δεν βρέθηκε κατάστημα", STORE_ID)
        return 1

    raw = EXCEL_PATH.read_bytes()
    parsed = parse_weekly_schedule_workbook(
        raw,
        employer_afm=str(cfg["employer_afm"]),
        branch_aa=str(cfg.get("branch_aa") or "0"),
    )
    targets = [
        row
        for row in parsed.get("rows") or []
        if str(row.get("import_action") or "") == "absent"
        and str(row.get("change_kind") or "") in ("new", "update")
        and not (row.get("validation_errors") or [])
    ]
    if not targets:
        print("Δεν υπάρχουν εκκρεμείς absent γραμμές προς αποστολή.")
        return 0

    print(f"Θα σταλούν {len(targets)} ΡΕΠΟ (absent) στο Ergani…")
    for row in targets:
        print(
            f"  {row.get('work_date')} | {row.get('eponymo')} {row.get('onoma')} | {row.get('employee_afm')}"
        )

    app = create_app()
    ok = 0
    fail = 0
    results: list[dict] = []

    with app.app_context():
        from flask import session

        with app.test_request_context("/"):
            session["active_store_id"] = STORE_ID
            ctx = store_api_context(cfg)
            bearer = ensure_ergani_bearer(ctx)
            if not bearer:
                print("ERROR: Αποτυχία σύνδεσης Ergani API")
                return 2

            batch_meta = {
                "batch_id": None,
                "original_filename": EXCEL_PATH.name,
                "week_label": (parsed.get("meta") or {}).get("week_label"),
            }
            for row in targets:
                row_for_apply = dict(row)
                row_for_apply["id"] = None
                try:
                    result = apply_import_row(ctx, row_for_apply, bearer, batch_meta=batch_meta)
                except Exception as ex:
                    result = {"success": False, "error": str(ex)}
                if result.get("success"):
                    ok += 1
                    print(
                        f"OK {row.get('eponymo')} {row.get('work_date')} protocol={result.get('protocol')}"
                    )
                else:
                    fail += 1
                    print(
                        f"FAIL {row.get('eponymo')} {row.get('work_date')}: {result.get('error')}"
                    )
                results.append(
                    {
                        "employee_afm": row.get("employee_afm"),
                        "work_date": row.get("work_date"),
                        "success": bool(result.get("success")),
                        "protocol": result.get("protocol"),
                        "error": result.get("error"),
                    }
                )

            dates = sorted(
                {ergani_date_to_iso(str(r.get("work_date") or "")) for r in targets},
                key=lambda d: d or "",
            )
            sync = None
            if ok and dates[0] and dates[-1]:
                try:
                    from app.schedule_sync import fetch_and_save_schedule_for_ctx

                    sync = fetch_and_save_schedule_for_ctx(
                        ctx,
                        from_iso=dates[0],
                        to_iso=dates[-1],
                        max_days=31,
                    )
                    print(
                        f"Συγχρονισμός ωραρίου {dates[0]}–{dates[-1]}: "
                        f"{'OK' if sync.get('success') else sync.get('detail') or 'αποτυχία'}"
                    )
                except Exception as ex:
                    print(f"Συγχρονισμός απέτυχε: {ex}")

            record_audit_event(
                action="schedule_import.absent_rest_batch",
                success=fail == 0,
                store_id=STORE_ID,
                employer_afm=str(cfg.get("employer_afm") or ""),
                branch_aa=str(cfg.get("branch_aa") or "0"),
                entity_type="schedule_import_batch",
                entity_id="absent_manual",
                details={
                    "source": "excel_absent_manual",
                    "original_filename": EXCEL_PATH.name,
                    "week_label": (parsed.get("meta") or {}).get("week_label"),
                    "applied": ok,
                    "failed": fail,
                    "results": results,
                    "schedule_sync": sync,
                },
            )

    print(f"Τέλος: επιτυχία {ok}, αποτυχία {fail}")
    return 0 if fail == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
