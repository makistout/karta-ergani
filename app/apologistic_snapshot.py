"""Generation of persisted weekly retrospective snapshots."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.apologistic import build_weekly_report, previous_week
from app.date_util import iso_to_ergani_dates
from app.repo_apologistic import mark_failed, save_report
from app.repo_employment_contract import list_current_for_store
from app.repo_schedule import list_schedule_for_range
from app.repo_work_log import list_work_log_for_range, normalize_overnight_work_log_rows

CALCULATION_VERSION = "2026-08-11.1"


def generate_store_week(store: dict[str, Any], week_from: date, week_to: date) -> dict[str, Any]:
    try:
        dates = iso_to_ergani_dates(week_from.isoformat(), week_to.isoformat(), 7)
        afm, branch = str(store["employer_afm"]), str(store["branch_aa"])
        schedule = list_schedule_for_range(afm, branch, dates)
        work_log = normalize_overnight_work_log_rows(
            list_work_log_for_range(afm, branch, dates),
            employer_afm=afm, branch_aa=branch, ergani_dates=dates,
        )
        contracts = list_current_for_store(afm, branch)
        report = build_weekly_report(schedule, work_log, contracts)
        saved = save_report(store=store, week_from=week_from, week_to=week_to,
                            report=report, calculation_version=CALCULATION_VERSION)
        return {"success": True, "store_id": int(store["id"]), "store_name": store.get("name"), **saved}
    except Exception as exc:
        mark_failed(store=store, week_from=week_from, week_to=week_to,
                    calculation_version=CALCULATION_VERSION, error=str(exc))
        return {"success": False, "store_id": int(store["id"]), "store_name": store.get("name"), "error": str(exc)}


def generate_previous_week(stores: list[dict[str, Any]], *, today: date | None = None) -> dict[str, Any]:
    week_from, week_to = previous_week(today)
    results = [generate_store_week(store, week_from, week_to) for store in stores]
    return {
        "success": all(row.get("success") for row in results),
        "from": week_from.isoformat(), "to": week_to.isoformat(),
        "stores": results, "ok_count": sum(bool(row.get("success")) for row in results),
        "fail_count": sum(not bool(row.get("success")) for row in results),
    }


def previous_week_for(local_day: date) -> tuple[date, date]:
    monday = local_day - timedelta(days=local_day.weekday())
    return monday - timedelta(days=7), monday - timedelta(days=1)
