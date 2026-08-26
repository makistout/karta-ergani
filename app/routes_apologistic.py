"""API for the previous-week retrospective work-time report."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from io import BytesIO

from flask import Blueprint, Response, jsonify, request, send_file, session

from app.apologistic import previous_week
from app.apologistic_export import build_apologistic_export_xlsx
from app.apologistic_submit import (
    load_apologistic_day_row,
    overtime_submit_group_from_row,
    parse_proposed_leave,
    schedule_body_from_apologistic_row,
    work_date_to_reference_iso,
)
from app.date_util import iso_to_ergani_dates
from app.http_helpers import resolve_active_store
from app.leave_payload import SUBMISSION_CODE_WTO_LEAVE, build_wto_leave_payload
from app.office_auth import SESSION_USER
from app.repo_apologistic import (
    apply_exchange, accept_all_review, accept_review, accept_uneven_distribution_group, reject_review,
    load_report, record_ergani_submit,
    enrich_employee_month_days, list_store_days, successful_overtime_minutes_for_year,
    restore_review_change, tables_available, update_proposed, update_overtime,
)
from app.repo_holidays import get_effective_holidays_for_store
from app.repo_schedule import list_schedule_for_range
from app.repo_store import get_sunday_rest_transfer_enabled
from app.repo_timekeeping import load_annual_overtime_context
from app.routes_wto_apologistic import execute_apologistic_wto_submit, json_submit_result
from app.wto_submit import parse_submit_response
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY_A, build_wto_daily_a_payload
from app.wto_ov_payload import SUBMISSION_CODE_WTO_OV_A, build_wto_ov_a_payload
from app.work_card_payload import WorkCardPayloadError
from app.timekeeping import build_timekeeping_report, is_timekeeping_leave_row
from app.timekeeping_export import (
    build_timekeeping_detailed_export_xlsx,
    build_timekeeping_export_xlsx,
)


apologistic_bp = Blueprint("apologistic", __name__, url_prefix="/api/apologistic")


class TimekeepingPeriodError(ValueError):
    def __init__(self, message: str, *, problem_weeks: list[dict[str, str]] | None = None):
        super().__init__(message)
        self.problem_weeks = problem_weeks or []


def _saved_range_response(ctx: dict, date_from: date, date_to: date):
    days = list_store_days(store_id=int(ctx["id"]), date_from=date_from, date_to=date_to)
    enrich_employee_month_days(
        store_id=int(ctx["id"]), employer_afm=str(ctx["employer_afm"]),
        branch_aa=str(ctx.get("branch_aa") or "0"), days=days,
    )
    employees = sorted({str(row.get("employee_afm") or "") for row in days if row.get("employee_afm")})
    work_dates = sorted({str(row.get("work_date") or "") for row in days}, key=lambda value: datetime.strptime(value, "%d/%m/%Y"))
    return {
        "store": {"id": ctx["id"], "name": ctx["name"], "employer_afm": ctx["employer_afm"],
                  "branch_aa": ctx["branch_aa"]},
        "from": date_from.isoformat(), "to": date_to.isoformat(), "work_dates": work_dates,
        "employees": employees, "days": days,
        "legal_notice": "Ελεγκτικό προσχέδιο από αποθηκευμένα αποτελέσματα. Οι εγγραφές «Έλεγχος» δεν αποτελούν αυτόματη δήλωση.",
    }


@apologistic_bp.get("/range")
def apologistic_range():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    try:
        date_from = datetime.strptime(str(request.args.get("from") or "")[:10], "%Y-%m-%d").date()
        date_to = datetime.strptime(str(request.args.get("to") or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Μη έγκυρο διάστημα"}), 400
    if date_to < date_from:
        return jsonify({"error": "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη"}), 400
    if (date_to - date_from).days > 366:
        return jsonify({"error": "Το διάστημα δεν μπορεί να υπερβαίνει το ένα έτος"}), 400
    _, latest_completed_to = previous_week()
    if date_to > latest_completed_to:
        return jsonify({"error": "Το διάστημα μπορεί να φτάνει έως την τελευταία ολοκληρωμένη εβδομάδα"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503
    return jsonify(_saved_range_response(ctx, date_from, date_to))


@apologistic_bp.get("/month")
def apologistic_month():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    today = date.today()
    try:
        year = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        month_from = date(year, month, 1)
        month_to = date(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError):
        return jsonify({"error": "Μη έγκυρος μήνας"}), 400
    if month_from > date(today.year, today.month, 1):
        return jsonify({"error": "Οι επόμενοι μήνες δεν είναι διαθέσιμοι στο απολογιστικό"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503

    payload = _saved_range_response(ctx, month_from, month_to)
    days = payload["days"]
    first_monday = month_from - timedelta(days=month_from.weekday())
    latest_completed, _ = previous_week()
    weeks = []
    cursor_week = first_monday
    saved_weeks = {str(row.get("week_from") or "")[:10] for row in days}
    while cursor_week <= month_to:
        week_to = cursor_week + timedelta(days=6)
        weeks.append({
            "from": cursor_week.isoformat(), "to": week_to.isoformat(),
            "visible_from": max(cursor_week, month_from).isoformat(),
            "visible_to": min(week_to, month_to).isoformat(),
            "available": cursor_week <= latest_completed and cursor_week.isoformat() in saved_weeks,
        })
        cursor_week += timedelta(days=7)
    return jsonify({**payload,
        "year": year, "month": month, "from": month_from.isoformat(), "to": month_to.isoformat(),
        "weeks": weeks,
    })


@apologistic_bp.get("/week")
def apologistic_week():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    default_from, default_to = previous_week()
    from_iso = request.args.get("from") or default_from.isoformat()
    to_iso = request.args.get("to") or default_to.isoformat()
    try:
        start = datetime.strptime(from_iso[:10], "%Y-%m-%d").date()
        end = datetime.strptime(to_iso[:10], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Μη έγκυρη ημερομηνία"}), 400
    if end < start or (end - start).days != 6 or start.weekday() != 0:
        return jsonify({"error": "Το διάστημα πρέπει να είναι εβδομάδα Δευτέρα–Κυριακή"}), 400
    if start > default_from:
        return jsonify({"error": "Η τρέχουσα και οι επόμενες εβδομάδες δεν είναι διαθέσιμες στο απολογιστικό"}), 400
    dates = iso_to_ergani_dates(from_iso, to_iso, 7)
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503
    loaded = load_report(int(ctx["id"]), start)
    if loaded is None:
        return jsonify({"error": "Δεν υπάρχει αποθηκευμένο απολογιστικό για αυτή την εβδομάδα"}), 404
    report, snapshot = loaded
    snapshot["source"] = "database"
    return jsonify({
        "store": {"id": ctx["id"], "name": ctx["name"], "employer_afm": ctx["employer_afm"],
                  "branch_aa": ctx["branch_aa"]},
        "from": from_iso, "to": to_iso, "work_dates": dates,
        "legal_notice": "Ελεγκτικό προσχέδιο. Οι εγγραφές «Έλεγχος» δεν αποτελούν αυτόματη δήλωση.",
        "snapshot": snapshot,
        **report,
    })


@apologistic_bp.post("/timekeeping/preview")
def apologistic_timekeeping_preview():
    """Calculate a read-only payroll timekeeping preview for one week or month."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        if body.get("year") is not None or body.get("month") is not None:
            year = int(body.get("year") or 0)
            month = int(body.get("month") or 0)
            result, snapshots, annual_context = _build_timekeeping_for_month(ctx, year=year, month=month)
            month_from = date(year, month, 1)
            month_to = date(year, month, monthrange(year, month)[1])
            return jsonify({
                **result,
                "store": {"id": ctx["id"], "name": ctx["name"]},
                "year": year,
                "month": month,
                "period_from": month_from.isoformat(),
                "period_to": month_to.isoformat(),
                "source_runs": snapshots,
                "annual_context": annual_context,
                "preview": True,
                "period_type": "month",
            })
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        if week_from.weekday() != 0:
            raise ValueError("Η εβδομάδα πρέπει να ξεκινά Δευτέρα")
        result, snapshot, annual_context = _build_timekeeping_for_week(ctx, week_from)
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except TimekeepingPeriodError as exc:
        return jsonify({"error": str(exc), "problem_weeks": exc.problem_weeks}), 409
    except ValueError as exc:
        status = 409 if "Σ ή Μ" in str(exc) else 400
        return jsonify({"error": str(exc)}), status
    return jsonify({
        **result,
        "store": {"id": ctx["id"], "name": ctx["name"]},
        "week_from": week_from.isoformat(),
        "week_to": (week_from + timedelta(days=6)).isoformat(),
        "source_run": snapshot,
        "annual_context": annual_context,
        "preview": True,
        "period_type": "week",
    })


def _build_timekeeping_for_week(ctx: dict, week_from: date):
    loaded = load_report(int(ctx["id"]), week_from)
    if loaded is None:
        raise LookupError("Δεν υπάρχει αποθηκευμένο απολογιστικό για αυτή την εβδομάδα")
    report, snapshot = loaded
    rows = list(report.get("days") or [])
    payroll_rows = [row for row in rows if not is_timekeeping_leave_row(row)]
    if any(str(row.get("status") or "").lower() == "review" for row in payroll_rows):
        raise ValueError("Η ωρομέτρηση είναι διαθέσιμη μόνο όταν όλες οι εγγραφές είναι Σ ή Μ")
    employee_afms = sorted({str(row.get("employee_afm") or "") for row in payroll_rows if row.get("employee_afm")})
    annual_context = load_annual_overtime_context(
        store_id=int(ctx["id"]), employee_afms=employee_afms, period_from=week_from,
    )
    holidays = get_effective_holidays_for_store(int(ctx["id"]), week_from.year)
    sunday_work_enabled = get_sunday_rest_transfer_enabled(int(ctx["id"]))
    next_week_context = _next_week_rest_context(ctx, week_from, employee_afms)
    result = build_timekeeping_report(
        rows, holidays=holidays, annual_context_by_employee=annual_context,
        sunday_work_enabled=sunday_work_enabled,
        next_week_context_by_employee=next_week_context,
    )
    return result, snapshot, annual_context


def _next_week_rest_context(
    ctx: dict, week_from: date, employee_afms: list[str],
) -> dict[str, dict[str, object]]:
    """Read next-week schedule once and count only explicit ΑΝΑΠΑΥΣΗ/ΡΕΠΟ days."""
    next_from = week_from + timedelta(days=7)
    next_to = next_from + timedelta(days=6)
    dates = iso_to_ergani_dates(next_from.isoformat(), next_to.isoformat(), 7)
    wanted = {str(value or "").strip() for value in employee_afms}
    rows = list_schedule_for_range(
        str(ctx["employer_afm"]), str(ctx.get("branch_aa") or "0"), dates,
    )
    by_employee_date: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        afm = str(row.get("employee_afm") or "").strip()
        if afm not in wanted:
            continue
        key = (afm, str(row.get("work_date") or "").strip())
        by_employee_date.setdefault(key, []).append(row)
    result: dict[str, dict[str, object]] = {}
    for afm in wanted:
        employee_groups = [items for (item_afm, _), items in by_employee_date.items() if item_afm == afm]
        explicit_rest_days = 0
        for items in employee_groups:
            has_work = any(str(item.get("hour_from") or "").strip() and str(item.get("hour_to") or "").strip() for item in items)
            markers = " ".join(str(item.get("shift_type") or "").upper() for item in items)
            if not has_work and ("ΑΝΑΠΑΥΣ" in markers or "ΡΕΠΟ" in markers):
                explicit_rest_days += 1
        result[afm] = {
            "known": bool(employee_groups),
            "explicit_rest_days": explicit_rest_days,
            "week_from": next_from.isoformat(),
            "week_to": next_to.isoformat(),
        }
    return result


def _merge_timekeeping_days(
    days: list[dict[str, object]], annual_after_by_employee: dict[str, int],
) -> dict[str, object]:
    premium_keys = ("day", "night", "sunday_holiday", "night_sunday_holiday")
    breakdown_families = (
        "overwork", "overtime_40", "overtime_60", "overtime_120",
        "partial_additional_12", "sixth_day", "exception",
    )
    employees: dict[str, dict[str, object]] = {}
    for day in days:
        afm = str(day.get("employee_afm") or "")
        total = employees.setdefault(afm, {
            "employee_afm": afm,
            "eponymo": day.get("eponymo") or "",
            "onoma": day.get("onoma") or "",
            "recognized_work_minutes": 0,
            "day": 0,
            "night": 0,
            "sunday_holiday": 0,
            "night_sunday_holiday": 0,
            "overtime_40": 0,
            "overtime_60": 0,
            "overtime_120": 0,
            "partial_additional_12": 0,
            "sixth_day_minutes": 0,
            "exception_minutes": 0,
        })
        total["recognized_work_minutes"] += int(day.get("recognized_work_minutes") or 0)
        for key, value in (day.get("premium_minutes") or {}).items():
            total[str(key)] += int(value or 0)
        for key in ("overtime_40", "overtime_60", "overtime_120", "partial_additional_12", "sixth_day_minutes", "exception_minutes"):
            total[key] += int(day.get(key) or 0)
        for family in breakdown_families:
            field = f"{family}_breakdown"
            target = total.setdefault(field, {key: 0 for key in premium_keys})
            for key in premium_keys:
                target[key] += int((day.get(field) or {}).get(key) or 0)
    for afm, total in employees.items():
        total["annual_legal_overtime_minutes_after_period"] = int(
            annual_after_by_employee.get(afm) or 0
        )
    return {
        "calculation_version": "timekeeping-v10-sixth-seventh-exception-month",
        "days": sorted(days, key=lambda item: (datetime.strptime(str(item["work_date"]), "%d/%m/%Y"), str(item["employee_afm"]))),
        "employees": sorted(employees.values(), key=lambda item: (str(item["eponymo"]), str(item["onoma"]), str(item["employee_afm"]))),
        "counts": {"days": len(days), "employees": len(employees)},
    }


def _build_timekeeping_for_month(ctx: dict, *, year: int, month: int):
    if not (1 <= month <= 12):
        raise ValueError("Μη έγκυρος μήνας")
    month_from = date(year, month, 1)
    month_to = date(year, month, monthrange(year, month)[1])
    month_rows = list_store_days(store_id=int(ctx["id"]), date_from=month_from, date_to=month_to)
    if not month_rows:
        raise LookupError("Δεν υπάρχει αποθηκευμένο απολογιστικό για αυτόν τον μήνα")
    week_starts = sorted({
        datetime.strptime(str(row.get("week_from") or "")[:10], "%Y-%m-%d").date()
        for row in month_rows if str(row.get("week_from") or "").strip()
    })
    if not week_starts:
        raise LookupError("Δεν βρέθηκαν αποθηκευμένες εβδομάδες για αυτόν τον μήνα")

    problem_weeks: list[dict[str, str]] = []
    initial_afms: set[str] = set()
    for week_from in week_starts:
        loaded = load_report(int(ctx["id"]), week_from)
        if loaded is None:
            raise LookupError(f"Λείπει αποθηκευμένο απολογιστικό για την εβδομάδα {week_from.isoformat()}")
        report, _ = loaded
        payroll_rows = [
            row for row in (report.get("days") or []) if not is_timekeeping_leave_row(row)
        ]
        if any(str(row.get("status") or "").lower() == "review" for row in payroll_rows):
            problem_weeks.append({
                "week_from": week_from.isoformat(),
                "week_to": (week_from + timedelta(days=6)).isoformat(),
                "label": f"{week_from:%d/%m}–{(week_from + timedelta(days=6)):%d/%m}",
            })
        initial_afms.update(
            str(row.get("employee_afm") or "") for row in payroll_rows if row.get("employee_afm")
        )
    if problem_weeks:
        raise TimekeepingPeriodError(
            "Η ωρομέτρηση μήνα είναι διαθέσιμη μόνο όταν όλες οι εβδομάδες είναι Σ ή Μ",
            problem_weeks=problem_weeks,
        )
    running_context = load_annual_overtime_context(
        store_id=int(ctx["id"]),
        employee_afms=sorted(initial_afms),
        period_from=week_starts[0],
    )

    merged_days: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    annual_after_by_employee: dict[str, int] = {}
    sunday_work_enabled = get_sunday_rest_transfer_enabled(int(ctx["id"]))
    for week_from in week_starts:
        loaded = load_report(int(ctx["id"]), week_from)
        if loaded is None:
            raise LookupError(f"Λείπει αποθηκευμένο απολογιστικό για την εβδομάδα {week_from.isoformat()}")
        report, snapshot = loaded
        holidays = get_effective_holidays_for_store(int(ctx["id"]), week_from.year)
        week_rows = list(report.get("days") or [])
        week_afms = sorted({str(row.get("employee_afm") or "") for row in week_rows if row.get("employee_afm")})
        week_result = build_timekeeping_report(
            week_rows,
            holidays=holidays,
            annual_context_by_employee=running_context,
            sunday_work_enabled=sunday_work_enabled,
            next_week_context_by_employee=_next_week_rest_context(ctx, week_from, week_afms),
        )
        snapshots.append({
            "id": snapshot.get("id"),
            "week_from": week_from.isoformat(),
            "week_to": (week_from + timedelta(days=6)).isoformat(),
            "status": snapshot.get("status"),
        })
        for employee in week_result.get("employees") or []:
            afm = str(employee.get("employee_afm") or "")
            annual_after = int(employee.get("annual_legal_overtime_minutes_after_period") or 0)
            annual_after_by_employee[afm] = annual_after
            meta = running_context.get(afm, {})
            running_context[afm] = {
                **meta,
                "legal_overtime_minutes_before_period": annual_after,
            }
        for day in week_result.get("days") or []:
            work_date = datetime.strptime(str(day.get("work_date") or ""), "%d/%m/%Y").date()
            if month_from <= work_date <= month_to:
                merged_days.append(day)
    return _merge_timekeeping_days(merged_days, annual_after_by_employee), snapshots, running_context


def _timekeeping_export_data(ctx: dict, body: dict):
    """Load the single canonical report used by every Excel projection."""
    if body.get("year") is not None or body.get("month") is not None:
        year = int(body.get("year") or 0)
        month = int(body.get("month") or 0)
        report, _, _ = _build_timekeeping_for_month(ctx, year=year, month=month)
        period_from = date(year, month, 1)
        period_to = date(year, month, monthrange(year, month)[1])
        return report, period_from, period_to, f"month_{year}{month:02d}", True
    week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
    if week_from.weekday() != 0:
        raise ValueError("Η εβδομάδα πρέπει να ξεκινά Δευτέρα")
    report, _, _ = _build_timekeeping_for_week(ctx, week_from)
    return report, week_from, week_from + timedelta(days=6), f"{week_from:%Y%m%d}", False


def _timekeeping_export_error(exc: Exception):
    if isinstance(exc, LookupError):
        return jsonify({"error": str(exc)}), 404
    if isinstance(exc, TimekeepingPeriodError):
        return jsonify({"error": str(exc), "problem_weeks": exc.problem_weeks}), 409
    status = 409 if "Σ ή Μ" in str(exc) else 400
    return jsonify({"error": str(exc)}), status


@apologistic_bp.post("/timekeeping/export")
def apologistic_timekeeping_export():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    try:
        report, period_from, period_to, filename_tag, is_month = _timekeeping_export_data(
            ctx, request.get_json(silent=True) or {},
        )
        content = build_timekeeping_export_xlsx(
            report=report,
            meta_line=f"{ctx['name']} · {period_from:%d/%m/%Y}–{period_to:%d/%m/%Y} · {report['calculation_version']}",
            title="Ωρομέτρηση μήνα" if is_month else "Ωρομέτρηση εβδομάδας",
            daily_title="Αναλυτική ωρομέτρηση μήνα ανά ημέρα" if is_month else "Αναλυτική ωρομέτρηση ανά ημέρα",
        )
    except LookupError as exc:
        return _timekeeping_export_error(exc)
    except TimekeepingPeriodError as exc:
        return _timekeeping_export_error(exc)
    except ValueError as exc:
        return _timekeeping_export_error(exc)
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"orometrisi_{filename_tag}.xlsx",
    )


@apologistic_bp.post("/timekeeping/export-detailed")
def apologistic_timekeeping_detailed_export():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    try:
        report, period_from, period_to, filename_tag, _ = _timekeeping_export_data(
            ctx, request.get_json(silent=True) or {},
        )
        content = build_timekeeping_detailed_export_xlsx(
            report=report,
            store=ctx,
            meta_line=f"{ctx['name']} · {period_from:%d/%m/%Y}–{period_to:%d/%m/%Y} · {report['calculation_version']}",
        )
    except (LookupError, TimekeepingPeriodError, ValueError) as exc:
        return _timekeeping_export_error(exc)
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"orometrisi_analysis_{filename_tag}.xlsx",
    )


@apologistic_bp.put("/proposal")
def apologistic_proposal_update():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        work_date = datetime.strptime(str(body.get("work_date") or ""), "%d/%m/%Y").date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = update_proposed(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            work_date=work_date, proposed=str(body.get("proposed") or ""),
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    loaded = load_report(int(ctx["id"]), week_from)
    history = []
    if loaded:
        history = next((row.get("proposal_history") or [] for row in loaded[0].get("days") or []
                        if row.get("employee_afm") == employee_afm and row.get("work_date") == work_date.strftime("%d/%m/%Y")), [])
    return jsonify({"success": True, **result, "history": history})


@apologistic_bp.put("/overtime")
def apologistic_overtime_update():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        work_date = datetime.strptime(str(body.get("work_date") or ""), "%d/%m/%Y").date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = update_overtime(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            work_date=work_date,
            overtime_from=body.get("overtime_from"),
            overtime_to=body.get("overtime_to"),
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/accept-review")
def apologistic_accept_review():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        work_date = datetime.strptime(str(body.get("work_date") or ""), "%d/%m/%Y").date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = accept_review(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            work_date=work_date, changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/exchange")
def apologistic_apply_exchange():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        rest_work_date = datetime.strptime(str(body.get("rest_work_date") or ""), "%d/%m/%Y").date()
        replacement_work_date = datetime.strptime(
            str(body.get("replacement_work_date") or ""), "%d/%m/%Y"
        ).date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = apply_exchange(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            rest_work_date=rest_work_date, replacement_work_date=replacement_work_date,
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/reject-review")
def apologistic_reject_review():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        work_date = datetime.strptime(str(body.get("work_date") or ""), "%d/%m/%Y").date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = reject_review(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            work_date=work_date, changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/restore-review")
def apologistic_restore_review():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        work_date = datetime.strptime(str(body.get("work_date") or ""), "%d/%m/%Y").date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = restore_review_change(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            work_date=work_date, changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/uneven-distribution/accept")
def apologistic_accept_uneven_distribution():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = accept_uneven_distribution_group(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            group_id=str(body.get("group_id") or ""),
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/accept-all-review")
def apologistic_accept_all_review():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Δεν υπάρχουν εγγραφές για έγκριση"}), 400
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        result = accept_all_review(
            store_id=int(ctx["id"]),
            week_from=week_from,
            items=items,
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.post("/export")
def apologistic_export():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503
    body = request.get_json(silent=True) or {}
    headers = body.get("headers") or []
    rows = body.get("rows") or []
    if not isinstance(headers, list) or not isinstance(rows, list):
        return jsonify({"error": "Μη έγκυρα δεδομένα εξαγωγής"}), 400
    if not headers or not rows:
        return jsonify({"error": "Δεν υπάρχουν αποτελέσματα για εξαγωγή"}), 400
    store_name = str(body.get("store_name") or ctx.get("name") or "").strip()
    period_label = str(body.get("period_label") or "").strip()
    filter_label = str(body.get("filter_label") or "").strip()
    meta_parts = [part for part in (store_name, period_label, filter_label) if part]
    meta_line = " · ".join(meta_parts) if meta_parts else "Απολογιστικό εβδομάδας"
    try:
        content = build_apologistic_export_xlsx(meta_line=meta_line, headers=headers, rows=rows)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    week_from = str(body.get("week_from") or "")[:10].replace("-", "")
    filename = f"apologistic_{week_from or 'week'}.xlsx"
    return Response(
        content,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_apologistic_lookup(body: dict) -> tuple[datetime.date, datetime.date, str]:
    week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
    work_date = datetime.strptime(str(body.get("work_date") or ""), "%d/%m/%Y").date()
    employee_afm = str(body.get("employee_afm") or "").strip()
    if len(employee_afm) != 9 or not employee_afm.isdigit():
        raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
    return week_from, work_date, employee_afm


def _persist_apologistic_submit(
    ctx: dict[str, Any],
    body: dict[str, Any],
    *,
    submission_code: str,
    resp,
    parsed,
    declaration_id: int | None,
    proposed_at_submit: str | None = None,
    segment_reference_date=None,
) -> dict[str, Any] | None:
    if not resp.ok:
        return None
    try:
        week_from, work_date, employee_afm = _parse_apologistic_lookup(body)
    except ValueError:
        return None
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    return record_ergani_submit(
        store_id=int(ctx["id"]),
        week_from=week_from,
        employee_afm=employee_afm,
        work_date=work_date,
        submission_code=submission_code,
        declaration_id=declaration_id,
        success=True,
        protocol=protocol,
        ergani_submission_id=ergani_id,
        submit_date_text=submit_date,
        proposed_at_submit=proposed_at_submit,
        segment_reference_date=segment_reference_date,
        submitted_by=str(session.get(SESSION_USER) or "").strip() or None,
    )


@apologistic_bp.post("/submit-schedule")
def apologistic_submit_schedule():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503

    try:
        if body.get("use_snapshot", True):
            week_from, work_date, employee_afm = _parse_apologistic_lookup(body)
            row = load_apologistic_day_row(
                store_id=int(ctx["id"]),
                week_from=week_from,
                employee_afm=employee_afm,
                work_date=work_date,
            )
            leave_type = parse_proposed_leave(str(row.get("proposed") or ""))
            if leave_type:
                if str(row.get("status") or row.get("result") or "").strip() != "change":
                    raise WorkCardPayloadError("Η γραμμή δεν έχει αποτέλεσμα «Μεταβολή»")
                payload = build_wto_leave_payload(
                    branch_aa=str(ctx.get("branch_aa") or "0"),
                    employee_afm=str(row.get("employee_afm") or ""),
                    employee_last_name=str(row.get("eponymo") or ""),
                    employee_first_name=str(row.get("onoma") or ""),
                    reference_date=work_date_to_reference_iso(str(row.get("work_date") or "")),
                    leave_type=leave_type,
                    comments=body.get("comments"),
                )
                resp, parsed, auth_retry, declaration_id = execute_apologistic_wto_submit(
                    ctx,
                    submission_code=SUBMISSION_CODE_WTO_LEAVE,
                    payload=payload,
                    audit_action="apologistic.submit_leave",
                    employee_afm=str(row.get("employee_afm") or ""),
                    reference_date=work_date_to_reference_iso(str(row.get("work_date") or "")),
                    audit_details={
                        "source": "apologistic",
                        "proposed": row.get("proposed"),
                        "leave_type": leave_type,
                        "week_from": str(body.get("week_from") or "")[:10] or None,
                        "work_date": str(body.get("work_date") or "").strip() or None,
                    },
                )
                if resp is None:
                    return jsonify(parsed), 401
                ergani_submit = _persist_apologistic_submit(
                    ctx,
                    body,
                    submission_code=SUBMISSION_CODE_WTO_LEAVE,
                    resp=resp,
                    parsed=parsed,
                    declaration_id=declaration_id,
                    proposed_at_submit=str(row.get("proposed") or "").strip() or None,
                )
                return json_submit_result(
                    submission_code=SUBMISSION_CODE_WTO_LEAVE,
                    resp=resp,
                    parsed=parsed,
                    auth_retry=auth_retry,
                    extra={"ergani_submit": ergani_submit} if ergani_submit else None,
                )
            schedule_body = schedule_body_from_apologistic_row(row)
        else:
            schedule_body = body
        payload = build_wto_daily_a_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=str(schedule_body["employee_afm"]),
            employee_last_name=str(schedule_body["eponymo"]),
            employee_first_name=str(schedule_body["onoma"]),
            reference_date=str(schedule_body["reference_date"]),
            schedule_type=str(schedule_body.get("schedule_type") or "ΕΡΓ"),
            hour_from=schedule_body.get("hour_from"),
            hour_to=schedule_body.get("hour_to"),
            intervals=schedule_body.get("intervals") if isinstance(schedule_body.get("intervals"), list) else None,
            comments=body.get("comments"),
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except WorkCardPayloadError as exc:
        return jsonify({"error": str(exc)}), 400

    resp, parsed, auth_retry, declaration_id = execute_apologistic_wto_submit(
        ctx,
        submission_code=SUBMISSION_CODE_WTO_DAILY_A,
        payload=payload,
        audit_action="apologistic.submit_schedule",
        employee_afm=str(schedule_body["employee_afm"]),
        reference_date=str(schedule_body["reference_date"]),
        audit_details={
            "source": "apologistic",
            "proposed": schedule_body.get("proposed"),
            "week_from": str(body.get("week_from") or "")[:10] or None,
            "work_date": str(body.get("work_date") or "").strip() or None,
        },
    )
    if resp is None:
        return jsonify(parsed), 401
    ergani_submit = _persist_apologistic_submit(
        ctx,
        body,
        submission_code=SUBMISSION_CODE_WTO_DAILY_A,
        resp=resp,
        parsed=parsed,
        declaration_id=declaration_id,
        proposed_at_submit=str(schedule_body.get("proposed") or "").strip() or None,
    )
    return json_submit_result(
        submission_code=SUBMISSION_CODE_WTO_DAILY_A,
        resp=resp,
        parsed=parsed,
        auth_retry=auth_retry,
        extra={"ergani_submit": ergani_submit} if ergani_submit else None,
    )


@apologistic_bp.post("/submit-overtime")
def apologistic_submit_overtime():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503

    try:
        if body.get("use_snapshot", True):
            week_from, work_date, employee_afm = _parse_apologistic_lookup(body)
            row = load_apologistic_day_row(
                store_id=int(ctx["id"]),
                week_from=week_from,
                employee_afm=employee_afm,
                work_date=work_date,
            )
            reference_date, day_segments = overtime_submit_group_from_row(
                row,
                segment_date_ergani=str(body.get("segment_date") or "").strip() or None,
            )
            submit_body = {
                "employee_afm": row.get("employee_afm"),
                "eponymo": row.get("eponymo"),
                "onoma": row.get("onoma"),
                "reference_date": reference_date,
                "intervals": [{"hour_from": s["hour_from"], "hour_to": s["hour_to"]} for s in day_segments],
            }
        else:
            submit_body = body
        payload = build_wto_ov_a_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=str(submit_body["employee_afm"]),
            employee_last_name=str(submit_body["eponymo"]),
            employee_first_name=str(submit_body["onoma"]),
            reference_date=str(submit_body["reference_date"]),
            hour_from=submit_body.get("hour_from"),
            hour_to=submit_body.get("hour_to"),
            intervals=submit_body.get("intervals") if isinstance(submit_body.get("intervals"), list) else None,
            comments=body.get("comments"),
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except WorkCardPayloadError as exc:
        return jsonify({"error": str(exc)}), 400

    reference_year = datetime.strptime(str(submit_body["reference_date"])[:10], "%Y-%m-%d").year
    submitted_minutes = successful_overtime_minutes_for_year(
        store_id=int(ctx["id"]), employee_afm=str(submit_body["employee_afm"]), year=reference_year,
    )
    new_minutes = 0
    for interval in submit_body.get("intervals") or [{"hour_from": submit_body.get("hour_from"), "hour_to": submit_body.get("hour_to")}]:
        start = datetime.strptime(str(interval.get("hour_from") or ""), "%H:%M")
        end = datetime.strptime(str(interval.get("hour_to") or ""), "%H:%M")
        minutes = int((end - start).total_seconds() // 60)
        new_minutes += minutes + (1440 if minutes < 0 else 0)
    projected_minutes = submitted_minutes + new_minutes
    if projected_minutes > 150 * 60 and not body.get("confirm_annual_limit"):
        return jsonify({
            "error": (
                f"Με τη νέα υποβολή οι επιτυχώς υποβλημένες υπερωρίες του {reference_year} "
                f"θα φτάσουν {projected_minutes // 60}:{projected_minutes % 60:02d}, πάνω από το όριο των 150 ωρών."
            ),
            "requires_confirmation": True,
            "annual_submitted_minutes": submitted_minutes,
            "new_overtime_minutes": new_minutes,
            "projected_annual_minutes": projected_minutes,
        }), 409

    resp, parsed, auth_retry, declaration_id = execute_apologistic_wto_submit(
        ctx,
        submission_code=SUBMISSION_CODE_WTO_OV_A,
        payload=payload,
        audit_action="apologistic.submit_overtime",
        employee_afm=str(submit_body["employee_afm"]),
        reference_date=str(submit_body["reference_date"]),
        audit_details={
            "source": "apologistic",
            "week_from": str(body.get("week_from") or "")[:10] or None,
            "work_date": str(body.get("work_date") or "").strip() or None,
            "segment_count": len(submit_body.get("intervals") or []) or (1 if submit_body.get("hour_from") else 0),
        },
    )
    if resp is None:
        return jsonify(parsed), 401
    segment_reference_date = None
    try:
        segment_reference_date = datetime.strptime(str(submit_body["reference_date"])[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    ergani_submit = _persist_apologistic_submit(
        ctx,
        body,
        submission_code=SUBMISSION_CODE_WTO_OV_A,
        resp=resp,
        parsed=parsed,
        declaration_id=declaration_id,
        segment_reference_date=segment_reference_date,
    )
    return json_submit_result(
        submission_code=SUBMISSION_CODE_WTO_OV_A,
        resp=resp,
        parsed=parsed,
        auth_retry=auth_retry,
        extra={"ergani_submit": ergani_submit} if ergani_submit else None,
    )
