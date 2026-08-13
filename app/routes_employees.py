"""API εργαζομένων — λίστα + στοιχεία σύμβασης (Μητρώα)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pyodbc
from flask import Blueprint, jsonify, request

from app.http_helpers import resolve_active_store
from app.portal_employment_contract_sync import iter_employment_contract_sync_events
from app.repo_employment_contract import (
    employment_contract_table_missing_message,
    list_current_for_store,
    list_history_for_employee,
)
from app.repo_entities import list_employees_for_employer
from app.sync_jobs import get_sync_job
from app.sync_route_util import start_async_portal_sync
from app.work_card_payload import norm_afm
from app.repo_apologistic import enrich_employee_month_days, list_employee_days
from app.apologistic import build_weekly_report
from app.date_util import iso_to_ergani_dates
from app.repo_schedule import list_schedule_for_range
from app.repo_work_log import list_work_log_for_range, normalize_overnight_work_log_rows

employees_bp = Blueprint("employees", __name__, url_prefix="/api/employees")


def _iso_rows(rows: list[dict]) -> list[dict]:
    for r in rows:
        for key in ("updated_at", "synced_at"):
            if hasattr(r.get(key), "isoformat"):
                r[key] = r[key].isoformat()
    return rows


def _contract_db_error(exc: Exception):
    msg = employment_contract_table_missing_message(exc)
    if msg:
        return jsonify({
            "error": msg,
            "contracts": [],
            "db_setup": "sql/alter_add_karta_employment_contract.sql",
        }), 503
    raise exc


@employees_bp.get("/list")
def employees_list():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "employees": []}), 400
    try:
        lim = int(request.args.get("limit", "2000"))
    except ValueError:
        lim = 2000
    rows = list_employees_for_employer(
        str(ctx["employer_afm"]),
        branch_aa=str(ctx.get("branch_aa") or "0"),
        limit=lim,
    )
    _iso_rows(rows)
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "employer_afm": ctx["employer_afm"],
        "branch_aa": ctx.get("branch_aa"),
        "count": len(rows),
        "employees": rows,
        "hint": (
            "Οι εργαζόμενοι συνδέονται με εργοδότη μέσω karta_employment "
            "(όχι απευθείας στο karta_employee). Η λίστα φιλτράρεται από το ενεργό σημείο."
        ),
    })


@employees_bp.get("/monthly-overview")
def employee_monthly_overview():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "days": []}), 400
    employee_afm = norm_afm(request.args.get("employee_afm") or request.args.get("afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm", "days": []}), 400
    today = date.today()
    try:
        year = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        month_from = date(year, month, 1)
    except (TypeError, ValueError):
        return jsonify({"error": "Μη έγκυρος μήνας", "days": []}), 400
    if month_from > today.replace(day=1):
        return jsonify({"error": "Δεν επιτρέπεται επιλογή μελλοντικού μήνα", "days": []}), 400
    month_to = date(year, month, calendar.monthrange(year, month)[1])
    snapshot_rows = list_employee_days(
        store_id=int(ctx["id"]), employee_afm=employee_afm,
        date_from=month_from, date_to=month_to,
    )
    by_date = {datetime.strptime(row["work_date"], "%d/%m/%Y").date(): row for row in snapshot_rows}

    # The persisted snapshot remains authoritative.  For dates not yet included
    # in a completed weekly run, show a clearly non-final live preview.
    current_week_from = today - timedelta(days=today.weekday())
    preview_from = max(month_from, current_week_from)
    preview_to = min(month_to, today)
    if month_from == today.replace(day=1) and preview_to >= preview_from:
        dates = iso_to_ergani_dates(preview_from.isoformat(), preview_to.isoformat(), 7)
        afm, branch = str(ctx["employer_afm"]), str(ctx.get("branch_aa") or "0")
        schedule = [row for row in list_schedule_for_range(afm, branch, dates)
                    if norm_afm(row.get("employee_afm") or "") == employee_afm]
        work_log = [row for row in normalize_overnight_work_log_rows(
            list_work_log_for_range(afm, branch, dates),
            employer_afm=afm, branch_aa=branch, ergani_dates=dates,
        ) if norm_afm(row.get("employee_afm") or "") == employee_afm]
        contracts = [row for row in list_current_for_store(afm, branch)
                     if norm_afm(row.get("employee_afm") or "") == employee_afm]
        preview = build_weekly_report(schedule, work_log, contracts)
        for item in preview.get("days") or []:
            work_date = datetime.strptime(item["work_date"], "%d/%m/%Y").date()
            if work_date not in by_date:
                item["source"] = "live_preview"
                item["finalized"] = False
                item["employee_afm"] = employee_afm
                item["week_from"] = (work_date - timedelta(days=work_date.weekday())).isoformat()
                by_date[work_date] = item

    employee_rows = list_employees_for_employer(
        str(ctx["employer_afm"]), branch_aa=str(ctx.get("branch_aa") or "0"), limit=5000,
    )
    employee = next((row for row in employee_rows if norm_afm(row.get("afm") or "") == employee_afm), {})
    days = []
    cursor_day = month_from
    while cursor_day <= month_to:
        row = by_date.get(cursor_day)
        if row:
            row.setdefault("employee_afm", employee_afm)
            row.setdefault("eponymo", employee.get("eponymo") or "")
            row.setdefault("onoma", employee.get("onoma") or "")
            days.append(row)
        else:
            days.append({
                "work_date": cursor_day.strftime("%d/%m/%Y"),
                "employee_afm": employee_afm,
                "eponymo": employee.get("eponymo") or "",
                "onoma": employee.get("onoma") or "",
                "source": "not_calculated" if cursor_day <= today else "future",
                "finalized": False,
            })
        cursor_day += timedelta(days=1)
    enrich_employee_month_days(
        store_id=int(ctx["id"]),
        employer_afm=str(ctx["employer_afm"]),
        branch_aa=str(ctx.get("branch_aa") or "0"),
        days=days,
    )
    return jsonify({
        "store": {"id": ctx["id"], "name": ctx["name"]},
        "employee": {
            "afm": employee_afm,
            "eponymo": employee.get("eponymo") or "",
            "onoma": employee.get("onoma") or "",
        },
        "year": year, "month": month,
        "current_year": today.year, "current_month": today.month,
        "count": len(snapshot_rows), "days": days,
        "legal_notice": "Ελεγκτικό προσχέδιο. Οι εγγραφές «Έλεγχος» δεν αποτελούν αυτόματη δήλωση.",
    })


@employees_bp.get("/contract/list")
def employment_contract_list():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "contracts": []}), 400
    try:
        lim = int(request.args.get("limit", "5000"))
    except ValueError:
        lim = 5000
    try:
        rows = list_current_for_store(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            limit=lim,
        )
    except pyodbc.Error as ex:
        return _contract_db_error(ex)
    _iso_rows(rows)
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "count": len(rows),
        "contracts": rows,
    })


@employees_bp.get("/contract/history")
def employment_contract_history():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "contracts": []}), 400
    employee_afm = norm_afm(request.args.get("employee_afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400
    try:
        lim = int(request.args.get("limit", "200"))
    except ValueError:
        lim = 200
    try:
        rows = list_history_for_employee(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            employee_afm,
            limit=lim,
        )
    except pyodbc.Error as ex:
        return _contract_db_error(ex)
    _iso_rows(rows)
    employee_name = ""
    if rows:
        employee_name = (
            f"{rows[0].get('eponymo') or ''} {rows[0].get('onoma') or ''}".strip()
        )
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "employee_afm": employee_afm,
        "employee_name": employee_name,
        "count": len(rows),
        "contracts": rows,
    })


@employees_bp.post("/contract/sync")
def employment_contract_sync_route():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    store_ctx = dict(ctx)
    return start_async_portal_sync(
        lambda job_id: iter_employment_contract_sync_events(
            store_ctx,
            run_id=job_id,
        ),
        label="employment_contract_sync",
        store_id=int(ctx["id"]),
    )


@employees_bp.get("/contract/sync/status/<job_id>")
def employment_contract_sync_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο ή ολοκληρωμένο job"}), 404
    return jsonify(job)
