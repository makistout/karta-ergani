"""Generation of persisted weekly retrospective snapshots."""

from __future__ import annotations

from datetime import date, timedelta
from time import perf_counter
from typing import Any

from app.apologistic import build_weekly_report, previous_week
from app.date_util import iso_to_ergani_dates
from app.karta_log import KartaLogger
from app import repo_sync_log
from app.repo_apologistic import mark_failed, save_report
from app.repo_employment_contract import list_history_for_store
from app.repo_entities import list_employees_for_employer
from app.repo_schedule import list_schedule_for_range
from app.repo_holidays import get_effective_holidays_for_store
from app.repo_store import get_action_settings, get_sunday_rest_transfer_enabled
from app.repo_work_log import list_work_log_for_range, normalize_overnight_work_log_rows

CALCULATION_VERSION = "2026-08-19.rules-v10-overnight-by-times"


def generate_store_week(store: dict[str, Any], week_from: date, week_to: date) -> dict[str, Any]:
    logger = KartaLogger(
        "scheduled_apologistic_snapshot",
        store_id=int(store["id"]),
        store_name=store.get("name"),
        extra={"week_from": week_from.isoformat(), "week_to": week_to.isoformat()},
    )
    started = perf_counter()
    logger.info(
        "Έναρξη εβδομαδιαίου απολογιστικού",
        week_from=week_from.isoformat(),
        week_to=week_to.isoformat(),
        calculation_version=CALCULATION_VERSION,
    )
    try:
        dates = iso_to_ergani_dates(week_from.isoformat(), week_to.isoformat(), 7)
        afm, branch = str(store["employer_afm"]), str(store["branch_aa"])
        schedule = list_schedule_for_range(afm, branch, dates)
        work_log = normalize_overnight_work_log_rows(
            list_work_log_for_range(afm, branch, dates),
            employer_afm=afm, branch_aa=branch, ergani_dates=dates,
        )
        contracts = list_history_for_store(afm, branch)
        employment_by_afm = {
            str(row.get("afm") or "").zfill(9): row
            for row in list_employees_for_employer(afm, branch_aa=branch, active_only=False)
        }
        for contract in contracts:
            employment = employment_by_afm.get(str(contract.get("employee_afm") or "").zfill(9), {})
            contract["hire_date"] = employment.get("hire_date")
            contract["departure_date"] = employment.get("departure_date")
            contract["effective_from"] = contract.get("ergani_updated_at")
        sunday_rest_transfer = get_sunday_rest_transfer_enabled(int(store["id"]))
        action_settings = get_action_settings(int(store["id"]))
        store_holidays = get_effective_holidays_for_store(int(store["id"]), week_from.year)
        report = build_weekly_report(
            schedule, work_log, contracts,
            sunday_rest_transfer_enabled=sunday_rest_transfer,
            uneven_distribution_enabled=bool(action_settings.get("uneven_distribution_enabled")),
            holiday_dates=store_holidays,
        )
        saved = save_report(store=store, week_from=week_from, week_to=week_to,
                            report=report, calculation_version=CALCULATION_VERSION)
        elapsed = round(perf_counter() - started, 3)
        result = {
            "success": True, "store_id": int(store["id"]), "store_name": store.get("name"),
            "week_from": week_from.isoformat(), "week_to": week_to.isoformat(),
            "elapsed_seconds": elapsed, **saved,
        }
        logger.info(
            "Ολοκλήρωση εβδομαδιαίου απολογιστικού",
            success=True,
            elapsed_seconds=elapsed,
            result_days=int(saved.get("days") or 0),
            run_id=saved.get("run_id"),
            skipped=bool(saved.get("skipped")),
        )
        repo_sync_log.finish_run(
            logger.run_id,
            status="done",
            message=f"Ολοκληρώθηκε σε {elapsed:.3f}s — {int(saved.get('days') or 0)} αποτελέσματα",
            result=result,
        )
        return result
    except Exception as exc:
        elapsed = round(perf_counter() - started, 3)
        try:
            mark_failed(store=store, week_from=week_from, week_to=week_to,
                        calculation_version=CALCULATION_VERSION, error=str(exc))
        except Exception:
            pass
        result = {
            "success": False, "store_id": int(store["id"]), "store_name": store.get("name"),
            "week_from": week_from.isoformat(), "week_to": week_to.isoformat(),
            "elapsed_seconds": elapsed, "error": str(exc),
        }
        logger.error(
            "Αποτυχία εβδομαδιαίου απολογιστικού",
            success=False,
            elapsed_seconds=elapsed,
            error=str(exc),
        )
        repo_sync_log.finish_run(
            logger.run_id,
            status="error",
            message=f"Αποτυχία μετά από {elapsed:.3f}s: {str(exc)[:350]}",
            result=result,
        )
        return result


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
