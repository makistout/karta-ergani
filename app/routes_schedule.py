"""API ψηφιακού ωραρίου — ξεχωριστό blueprint."""

from __future__ import annotations

import pyodbc
from flask import Blueprint, jsonify, request

from app.date_util import format_date_for_ergani, iso_to_ergani_dates
from app.http_helpers import resolve_active_store
from app.repo_schedule import (
    list_schedule_for_range,
    list_schedule_for_store,
    schedule_table_missing_message,
)
from app.schedule_sync import fetch_and_save_schedule_for_ctx

schedule_bp = Blueprint("schedule", __name__, url_prefix="/api/schedule")


def _schedule_db_error(exc: Exception):
    msg = schedule_table_missing_message(exc)
    if msg:
        return jsonify({"error": msg, "schedule": [], "db_setup": "sql/alter_add_karta_schedule.sql"}), 503
    raise exc


def _resolve_dates() -> tuple[str | None, str | None, list[str]]:
    from_iso = request.args.get("from") or request.args.get("date")
    to_iso = request.args.get("to") or from_iso
    if not from_iso:
        return None, None, []
    ergani_dates = iso_to_ergani_dates(from_iso, to_iso, 31)
    return from_iso, to_iso, ergani_dates


@schedule_bp.get("/list")
def schedule_list():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "schedule": []}), 400
    from_iso, to_iso, ergani_dates = _resolve_dates()
    if not from_iso:
        return jsonify({"error": "Λείπει παράμετρος date ή from/to"}), 400
    try:
        if len(ergani_dates) <= 1:
            rows = list_schedule_for_store(
                ctx["employer_afm"],
                ctx["branch_aa"],
                ergani_dates[0],
            )
        else:
            rows = list_schedule_for_range(
                ctx["employer_afm"],
                ctx["branch_aa"],
                ergani_dates,
            )
    except pyodbc.Error as ex:
        return _schedule_db_error(ex)
    for r in rows:
        if hasattr(r.get("synced_at"), "isoformat"):
            r["synced_at"] = r["synced_at"].isoformat()
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx["branch_aa"],
        },
        "from": from_iso,
        "to": to_iso,
        "work_date": ergani_dates[0] if len(ergani_dates) == 1 else None,
        "work_dates": ergani_dates,
        "count": len(rows),
        "schedule": rows,
    })


@schedule_bp.post("/sync")
def schedule_sync():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    data = request.get_json(silent=True) or {}
    from_iso = data.get("from") or data.get("date") or request.args.get("date")
    to_iso = data.get("to") or from_iso
    try:
        result = fetch_and_save_schedule_for_ctx(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=31,
        )
    except pyodbc.Error as ex:
        msg = schedule_table_missing_message(ex)
        if msg:
            return jsonify({
                "success": False,
                "error": msg,
                "db_setup": "sql/alter_add_karta_schedule.sql",
            }), 503
        raise
    return jsonify({
        "success": result.get("success"),
        "sync": result,
        "error": result.get("detail") if not result.get("success") else None,
    })
