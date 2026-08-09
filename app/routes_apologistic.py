"""API for the previous-week retrospective work-time report."""

from __future__ import annotations

from datetime import datetime

import pyodbc
from flask import Blueprint, jsonify, request

from app.apologistic import build_weekly_report, previous_week
from app.date_util import iso_to_ergani_dates
from app.http_helpers import resolve_active_store
from app.repo_employment_contract import list_current_for_store
from app.repo_schedule import list_schedule_for_range
from app.repo_work_log import list_work_log_for_range, normalize_overnight_work_log_rows


apologistic_bp = Blueprint("apologistic", __name__, url_prefix="/api/apologistic")


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
    dates = iso_to_ergani_dates(from_iso, to_iso, 7)
    try:
        schedule = list_schedule_for_range(ctx["employer_afm"], ctx["branch_aa"], dates)
        work_log = list_work_log_for_range(ctx["employer_afm"], ctx["branch_aa"], dates)
        work_log = normalize_overnight_work_log_rows(
            work_log, employer_afm=ctx["employer_afm"], branch_aa=ctx["branch_aa"], ergani_dates=dates
        )
        contracts = list_current_for_store(ctx["employer_afm"], ctx["branch_aa"])
    except pyodbc.Error as exc:
        return jsonify({"error": f"Σφάλμα ανάγνωσης δεδομένων: {exc}"}), 503
    report = build_weekly_report(schedule, work_log, contracts)
    return jsonify({
        "store": {"id": ctx["id"], "name": ctx["name"], "employer_afm": ctx["employer_afm"],
                  "branch_aa": ctx["branch_aa"]},
        "from": from_iso, "to": to_iso, "work_dates": dates,
        "legal_notice": "Ελεγκτικό προσχέδιο. Οι εγγραφές «Έλεγχος» δεν αποτελούν αυτόματη δήλωση.",
        **report,
    })
