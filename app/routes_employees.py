"""API εργαζομένων — λίστα + στοιχεία σύμβασης (Μητρώα)."""

from __future__ import annotations

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
