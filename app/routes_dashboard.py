"""Αναφορές αρχικής σελίδας."""

from __future__ import annotations

from datetime import datetime

import pyodbc
from flask import Blueprint, jsonify, request

from app.card_report import build_card_status_report
from app.http_helpers import resolve_active_store
from app.work_card_payload import tz_athens
from app.repo_schedule import schedule_table_missing_message
from app.repo_work_log import work_log_table_missing_message

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


def _db_error(exc: Exception):
    msg = schedule_table_missing_message(exc) or work_log_table_missing_message(exc)
    if msg:
        return jsonify({"error": msg, "rows": [], "summary": {}}), 503
    raise exc


@dashboard_bp.get("/card-report")
def card_report():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "rows": []}), 400

    raw = request.args.get("date") or request.args.get("from")
    if raw and "/" in str(raw)[:10]:
        try:
            d = datetime.strptime(str(raw).strip()[:10], "%d/%m/%Y")
            date_iso = d.strftime("%Y-%m-%d")
        except ValueError:
            date_iso = str(raw).strip()[:10]
    elif raw:
        date_iso = str(raw).strip()[:10]
    else:
        date_iso = datetime.now(tz_athens()).date().isoformat()

    try:
        report = build_card_status_report(
            ctx["employer_afm"],
            ctx["branch_aa"],
            date_iso=date_iso,
        )
    except pyodbc.Error as ex:
        return _db_error(ex)

    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx["branch_aa"],
        },
        **report,
    })
