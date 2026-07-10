"""API φόρμας ημερήσιου ωραρίου (HTML) — /ui/schedule."""

from __future__ import annotations

import pyodbc
from flask import Blueprint, jsonify, request

from app.http_helpers import resolve_active_store
from app.repo_schedule import schedule_table_missing_message
from app.schedule_day_form_service import build_day_form, preview_day_form, submit_day_form

schedule_day_form_bp = Blueprint("schedule_day_form", __name__, url_prefix="/api/schedule/day-form")


def _db_error(exc: Exception):
    msg = schedule_table_missing_message(exc)
    if msg:
        return jsonify({"error": msg, "db_setup": "sql/alter_add_karta_schedule.sql"}), 503
    raise exc


def _date_iso_from_request() -> str | None:
    raw = request.args.get("date") if request.method == "GET" else None
    if raw is None and request.is_json:
        body = request.get_json(silent=True) or {}
        raw = body.get("date") or body.get("date_iso")
    if not raw:
        return None
    s = str(raw).strip()[:10]
    if "/" in s:
        from datetime import datetime
        try:
            return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None
    return s if len(s) >= 10 else None


@schedule_day_form_bp.get("")
def day_form_get():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    date_iso = _date_iso_from_request()
    if not date_iso:
        return jsonify({"error": "Λείπει date (YYYY-MM-DD)"}), 400
    try:
        payload = build_day_form(ctx, date_iso=date_iso)
    except pyodbc.Error as ex:
        return _db_error(ex)
    return jsonify({"success": True, **payload})


@schedule_day_form_bp.post("/preview")
def day_form_preview():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    date_iso = _date_iso_from_request() or str(body.get("date") or body.get("date_iso") or "")[:10]
    if not date_iso:
        return jsonify({"error": "Λείπει date"}), 400
    rows = body.get("rows") if isinstance(body.get("rows"), list) else []
    try:
        preview = preview_day_form(ctx, date_iso=date_iso, form_rows=rows)
    except pyodbc.Error as ex:
        return _db_error(ex)
    return jsonify({"success": True, **preview})


@schedule_day_form_bp.post("/submit")
def day_form_submit():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    date_iso = str(body.get("date") or body.get("date_iso") or "")[:10]
    if not date_iso:
        return jsonify({"error": "Λείπει date"}), 400
    rows = body.get("rows") if isinstance(body.get("rows"), list) else []
    try:
        result = submit_day_form(ctx, date_iso=date_iso, form_rows=rows)
    except pyodbc.Error as ex:
        return _db_error(ex)
    status = 200 if result.get("success") else 502
    if result.get("error") and not rows:
        status = 400
    return jsonify(result), status
