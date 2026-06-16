"""API μηνιαίας κατάστασης (EX_BASE_04)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.http_helpers import ensure_ergani_bearer, resolve_active_store
from app.monthly_status_sync import iter_monthly_status_sync_events
from app.repo_monthly_status import list_monthly_status, monthly_status_table_missing_message
from app.sync_jobs import get_sync_job
from app.sync_route_util import start_async_portal_sync

monthly_status_bp = Blueprint("monthly_status", __name__, url_prefix="/api/monthly-status")


def _parse_year_month(data: dict) -> tuple[int | None, int | None, str | None]:
    try:
        year = int(data.get("year") or data.get("report_year") or 0)
        month = int(data.get("month") or data.get("report_month") or 0)
    except (TypeError, ValueError):
        return None, None, "Μη έγκυρο έτος ή μήνας"
    if year < 2000 or year > 2100:
        return None, None, "Μη έγκυρο έτος"
    if month < 1 or month > 12:
        return None, None, "Μη έγκυρος μήνας (1–12)"
    return year, month, None


@monthly_status_bp.get("/list")
def monthly_status_list():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "rows": []}), 400
    year_arg = request.args.get("year") or request.args.get("report_year")
    month_arg = request.args.get("month") or request.args.get("report_month")
    employee_afm = (request.args.get("afm") or request.args.get("employee_afm") or "").strip() or None
    report_year = int(year_arg) if year_arg else None
    report_month = int(month_arg) if month_arg else None
    try:
        lim = int(request.args.get("limit", "5000"))
    except ValueError:
        lim = 5000
    try:
        rows = list_monthly_status(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            report_year=report_year,
            report_month=report_month,
            employee_afm=employee_afm,
            limit=lim,
        )
    except Exception as ex:
        hint = monthly_status_table_missing_message(ex)
        if hint:
            return jsonify({"error": hint, "rows": [], "db_setup": hint}), 500
        raise
    for r in rows:
        if hasattr(r.get("synced_at"), "isoformat"):
            r["synced_at"] = r["synced_at"].isoformat()
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "report_year": report_year,
        "report_month": report_month,
        "employee_afm": employee_afm,
        "count": len(rows),
        "rows": rows,
    })


@monthly_status_bp.post("/sync")
def monthly_status_sync():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({
            "error": "Αποτυχία σύνδεσης Ergani — επιλέξτε ξανά το κατάστημα",
        }), 401

    data = request.get_json(silent=True) or {}
    year, month, err = _parse_year_month(data)
    if err:
        return jsonify({"error": err}), 400

    store_ctx = dict(ctx)
    return start_async_portal_sync(
        lambda job_id: iter_monthly_status_sync_events(
            store_ctx,
            bearer,
            year,
            month,
            run_id=job_id,
        ),
        label="monthly_status_sync",
        store_id=int(ctx["id"]),
    )


@monthly_status_bp.get("/sync/status/<job_id>")
def monthly_status_sync_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο ή ολοκληρωμένο job"}), 404
    return jsonify(job)
