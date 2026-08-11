"""API for the previous-week retrospective work-time report."""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request, session

from app.apologistic import previous_week
from app.date_util import iso_to_ergani_dates
from app.http_helpers import resolve_active_store
from app.office_auth import SESSION_USER
from app.repo_apologistic import load_report, tables_available, update_proposed


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
