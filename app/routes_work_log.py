"""API πραγματικής απασχόλησης — ξεχωριστό blueprint."""

from __future__ import annotations

import math
from datetime import datetime

import pyodbc
from flask import Blueprint, jsonify, request

from app.date_util import iso_to_ergani_dates
from app.http_helpers import resolve_active_store
from app.portal_work_log_sync import iter_work_log_sync_events
from app.sync_jobs import get_sync_job
from app.sync_route_util import (
    parse_sync_request,
    should_run_async,
    start_async_portal_sync,
)
from app.repo_work_log import (
    list_work_log_for_range,
    list_work_log_for_store,
    list_work_log_history_for_employee,
    work_log_table_missing_message,
    enrich_work_log_rows_with_schedule,
    enrich_work_log_history_with_card_punch,
    enrich_work_log_rows_with_card_punch,
    list_work_log_missing_cards_paged,
)
from app.repo_schedule import schedule_table_missing_message
from app.work_card_payload import norm_afm, tz_athens
from app.work_log_sync import fetch_and_save_work_log_for_ctx

work_log_bp = Blueprint("work_log", __name__, url_prefix="/api/work-log")


def _db_error(exc: Exception):
    msg = work_log_table_missing_message(exc)
    if msg:
        return jsonify({
            "error": msg,
            "work_log": [],
            "db_setup": "sql/alter_add_karta_work_log.sql",
        }), 503
    raise exc


def _dates_from_request():
    from_iso = request.args.get("from") or request.args.get("date")
    to_iso = request.args.get("to") or from_iso
    if not from_iso:
        return None, None, []
    return from_iso, to_iso, iso_to_ergani_dates(from_iso, to_iso, 31)


@work_log_bp.get("/list")
def work_log_list():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "work_log": []}), 400
    from_iso, to_iso, ergani_dates = _dates_from_request()
    if not from_iso:
        return jsonify({"error": "Λείπει date ή from/to"}), 400
    try:
        if len(ergani_dates) <= 1:
            rows = list_work_log_for_store(
                ctx["employer_afm"], ctx["branch_aa"], ergani_dates[0]
            )
        else:
            rows = list_work_log_for_range(
                ctx["employer_afm"], ctx["branch_aa"], ergani_dates
            )
    except pyodbc.Error as ex:
        return _db_error(ex)
    try:
        enrich_work_log_rows_with_schedule(
            rows, ctx["employer_afm"], ctx["branch_aa"], ergani_dates
        )
    except pyodbc.Error as ex:
        if not schedule_table_missing_message(ex):
            raise
        for r in rows:
            r["schedule_label"] = "—"
            r["schedule"] = None
    try:
        enrich_work_log_rows_with_card_punch(
            rows, ctx["employer_afm"], ctx["branch_aa"]
        )
    except pyodbc.Error as ex:
        if not schedule_table_missing_message(ex):
            raise
    try:
        from app.repo_today_alert import enrich_work_log_rows_with_today_notify_snooze

        enrich_work_log_rows_with_today_notify_snooze(
            rows, int(ctx["id"]), ergani_dates
        )
    except pyodbc.Error:
        for r in rows:
            r.setdefault("today_notify_snoozed", False)
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
        "work_dates": ergani_dates,
        "count": len(rows),
        "work_log": rows,
    })


@work_log_bp.get("/history")
def work_log_history():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "work_log": []}), 400
    employee_afm = norm_afm(request.args.get("employee_afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400
    try:
        rows = list_work_log_history_for_employee(
            ctx["employer_afm"],
            ctx["branch_aa"],
            employee_afm,
        )
    except pyodbc.Error as ex:
        return _db_error(ex)
    try:
        enrich_work_log_history_with_card_punch(
            rows, ctx["employer_afm"], ctx["branch_aa"], employee_afm
        )
    except pyodbc.Error as ex:
        if not schedule_table_missing_message(ex):
            raise
    for r in rows:
        if hasattr(r.get("synced_at"), "isoformat"):
            r["synced_at"] = r["synced_at"].isoformat()
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
            "branch_aa": ctx["branch_aa"],
        },
        "employee_afm": employee_afm,
        "employee_name": employee_name,
        "count": len(rows),
        "work_log": rows,
    })


@work_log_bp.get("/missing-cards")
def work_log_missing_cards():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "work_log": []}), 400
    page = max(1, int(request.args.get("page") or 1))
    page_size = max(1, min(int(request.args.get("page_size") or 20), 100))
    closed_page = max(1, int(request.args.get("closed_page") or 1))
    closed_page_size = max(1, min(int(request.args.get("closed_page_size") or 20), 100))
    today_ergani = datetime.now(tz_athens()).strftime("%d/%m/%Y")
    try:
        rows, total, closed_rows, closed_total = list_work_log_missing_cards_paged(
            ctx["employer_afm"],
            ctx["branch_aa"],
            today_ergani,
            page=page,
            page_size=page_size,
            closed_page=closed_page,
            closed_page_size=closed_page_size,
            store_id=int(ctx["id"]),
        )
    except pyodbc.Error as ex:
        return _db_error(ex)
    all_rows = rows + closed_rows
    dates = list(
        dict.fromkeys(
            str(r.get("work_date") or "").strip()
            for r in all_rows
            if (r.get("work_date") or "").strip()
        )
    )
    try:
        enrich_work_log_rows_with_schedule(
            all_rows, ctx["employer_afm"], ctx["branch_aa"], dates
        )
    except pyodbc.Error as ex:
        if not schedule_table_missing_message(ex):
            raise
        for r in all_rows:
            r["schedule_label"] = "—"
            r["schedule"] = None
    try:
        enrich_work_log_rows_with_card_punch(
            rows, ctx["employer_afm"], ctx["branch_aa"]
        )
    except pyodbc.Error as ex:
        if not schedule_table_missing_message(ex):
            raise
    for r in all_rows:
        if hasattr(r.get("synced_at"), "isoformat"):
            r["synced_at"] = r["synced_at"].isoformat()
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    closed_total_pages = (
        max(1, math.ceil(closed_total / closed_page_size)) if closed_total else 1
    )
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx["branch_aa"],
        },
        "exclude_date": today_ergani,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "count": len(rows),
        "work_log": rows,
        "closed_page": closed_page,
        "closed_page_size": closed_page_size,
        "closed_total": closed_total,
        "closed_total_pages": closed_total_pages,
        "closed_count": len(closed_rows),
        "closed_work_log": closed_rows,
    })


@work_log_bp.post("/sync")
def work_log_sync_route():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    data = request.get_json(silent=True) or {}
    from_iso, to_iso, dates = parse_sync_request(data)
    if not from_iso:
        return jsonify({"error": "Λείπει date ή from/to"}), 400

    if should_run_async(data, dates):
        store_ctx = dict(ctx)
        return start_async_portal_sync(
            lambda job_id: iter_work_log_sync_events(
                store_ctx,
                from_iso=from_iso,
                to_iso=to_iso,
                max_days=31,
                run_id=job_id,
            ),
            label="work_log_sync",
            store_id=int(ctx["id"]),
        )

    try:
        result = fetch_and_save_work_log_for_ctx(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=31,
        )
    except pyodbc.Error as ex:
        msg = work_log_table_missing_message(ex)
        if msg:
            return jsonify({
                "success": False,
                "error": msg,
                "db_setup": "sql/alter_add_karta_work_log.sql",
            }), 503
        raise
    return jsonify({
        "success": result.get("success"),
        "sync": result,
        "error": result.get("detail") if not result.get("success") else None,
    })


@work_log_bp.get("/sync/status/<job_id>")
def work_log_sync_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο ή ολοκληρωμένο job"}), 404
    return jsonify(job)
