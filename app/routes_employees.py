"""API εργαζομένων — λίστα + στοιχεία σύμβασης (Μητρώα)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

import pyodbc
from flask import Blueprint, jsonify, request

from app.http_helpers import resolve_active_store
from app.portal_employment_contract_sync import iter_employment_contract_sync_events
from app.repo_employment_contract import (
    employment_contract_table_missing_message,
    list_current_for_store,
    list_history_for_employee,
)
from app.repo_entities import (
    list_employees_for_employer, update_employment_dates,
    update_employment_catering_override,
    get_employment_work_time_qr,
)
from app.sync_jobs import get_sync_job
from app.sync_route_util import start_async_portal_sync
from app.work_card_payload import norm_afm
from app.repo_apologistic import enrich_employee_month_days, list_employee_days
from app.apologistic import build_weekly_report
from app.date_util import iso_to_ergani_dates
from app.repo_schedule import list_schedule_for_range
from app.repo_employee_leave import (
    load_current_year_normal_leave,
    load_schedule_archive_latest_month,
)
from app.repo_work_log import (
    count_incomplete_punches_by_employee_for_month,
    list_work_log_for_range,
    normalize_overnight_work_log_rows,
)

employees_bp = Blueprint("employees", __name__, url_prefix="/api/employees")


def _optional_iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _contract_summary(contract: dict | None) -> str | None:
    if not contract:
        return None
    text = " ".join(
        str(contract.get(key) or "").upper()
        for key in ("characterization", "regime", "employment_relation")
    )
    days_raw = str(contract.get("weekly_work_days") or "")
    days = next((n for n in (5, 6) if str(n) in days_raw), None)
    if "ΕΚ ΠΕΡΙΤΡΟΠ" in text:
        kind = "Εκ περιτροπής"
    elif "ΜΕΡΙΚ" in text:
        kind = "Μερική"
    elif "ΠΛΗΡ" in text:
        kind = "Πλήρης"
    else:
        specialty = str(contract.get("specialty") or "").strip()
        return specialty or None
    if days:
        return f"{kind} · {days}ημ."
    return kind


def _annual_normal_leave_entitlement(contract: dict | None) -> int | None:
    """Annual normal-leave entitlement used by the employee list (5-day/6-day)."""
    if not contract:
        return None
    days_raw = str(contract.get("weekly_work_days") or "")
    if "6" in days_raw:
        return 26
    if "5" in days_raw:
        return 22
    return None


def _iso_rows(rows: list[dict]) -> list[dict]:
    for r in rows:
        for key in ("updated_at", "synced_at", "last_checked_at", "hire_date", "departure_date"):
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
    employer_afm = str(ctx["employer_afm"])
    branch_aa = str(ctx.get("branch_aa") or "0")
    rows = list_employees_for_employer(
        employer_afm, branch_aa=branch_aa, limit=lim, active_only=False
    )
    contracts_by_afm: dict[str, dict] = {}
    try:
        for contract in list_current_for_store(employer_afm, branch_aa, limit=lim):
            afm = norm_afm(str(contract.get("employee_afm") or ""))
            if afm:
                contracts_by_afm[afm] = contract
    except pyodbc.Error:
        contracts_by_afm = {}
    open_punches = count_incomplete_punches_by_employee_for_month(employer_afm, branch_aa)
    today = date.today()
    employee_afms = [
        norm_afm(str(row.get("afm") or "")) for row in rows
        if norm_afm(str(row.get("afm") or ""))
    ]
    try:
        normal_leave = load_current_year_normal_leave(
            store_id=int(ctx["id"]), employee_afms=employee_afms, today=today,
        )
        leave_latest_month = load_schedule_archive_latest_month(store_id=int(ctx["id"]))
    except pyodbc.Error:
        normal_leave = {}
        leave_latest_month = None
    for row in rows:
        afm = norm_afm(str(row.get("afm") or ""))
        contract = contracts_by_afm.get(afm)
        row["contract_label"] = _contract_summary(contract)
        row["open_punches_month"] = int(open_punches.get(afm) or 0)
        leave = normal_leave.get(afm)
        row["normal_leave_days_taken"] = int(leave["days_taken"]) if leave else None
        row["normal_leave_entitled_days"] = _annual_normal_leave_entitlement(contract)
    _iso_rows(rows)
    active_count = sum(1 for row in rows if row.get("active") not in (False, 0))
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
        "active_count": active_count,
        "inactive_count": len(rows) - active_count,
        "employees": rows,
        "open_punches_month_label": f"{today.strftime('%m/%Y')}",
        "normal_leave_latest_month": (
            leave_latest_month.strftime("%m/%Y") if leave_latest_month else None
        ),
        "hint": (
            "Οι εργαζόμενοι συνδέονται με εργοδότη μέσω karta_employment "
            "(όχι απευθείας στο karta_employee). Η λίστα φιλτράρεται από το ενεργό σημείο."
        ),
    })


@employees_bp.get("/work-time-qr")
def employee_work_time_qr():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    employee_afm = norm_afm(request.args.get("employee_afm") or request.args.get("afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400
    row = get_employment_work_time_qr(
        str(ctx["employer_afm"]),
        str(ctx.get("branch_aa") or "0"),
        employee_afm,
    )
    if not row:
        return jsonify({"error": "Δεν βρέθηκε εργαζόμενος στο ενεργό κατάστημα"}), 404
    for key in ("work_time_qr_synced_at",):
        if hasattr(row.get(key), "isoformat"):
            row[key] = row[key].isoformat()
    qr = str(row.get("work_time_qr_data_url") or "").strip()
    return jsonify({
        "employee": {
            "afm": row.get("employee_afm"),
            "eponymo": row.get("eponymo") or "",
            "onoma": row.get("onoma") or "",
        },
        "business": {
            "afm": row.get("employer_afm"),
            "eponimia": row.get("employer_eponimia") or "",
            "branch_aa": row.get("branch_aa") or "",
            "branch_desc": row.get("branch_desc") or "",
        },
        "qr_data_url": qr or None,
        "has_qr": bool(qr),
        "synced_at": row.get("work_time_qr_synced_at"),
    })


@employees_bp.patch("/employment-dates")
def employee_employment_dates_update():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    payload = request.get_json(silent=True) or {}
    employee_afm = norm_afm(payload.get("employee_afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400
    try:
        hire = _optional_iso_date(payload.get("hire_date"))
        departure = _optional_iso_date(payload.get("departure_date"))
    except ValueError:
        return jsonify({"error": "Οι ημερομηνίες πρέπει να είναι YYYY-MM-DD"}), 400
    if hire and departure and departure < hire:
        return jsonify({"error": "Η αποχώρηση δεν μπορεί να είναι πριν από την πρόσληψη"}), 400
    try:
        update_employment_dates(
            str(ctx["employer_afm"]), str(ctx.get("branch_aa") or "0"), employee_afm,
            hire_date=hire, departure_date=departure,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({
        "ok": True, "employee_afm": employee_afm,
        "hire_date": hire.isoformat() if hire else None,
        "departure_date": departure.isoformat() if departure else None,
    })


@employees_bp.patch("/catering-override")
def employee_catering_override_update():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    payload = request.get_json(silent=True) or {}
    employee_afm = norm_afm(payload.get("employee_afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400
    raw = payload.get("catering_override")
    if raw not in (None, True, False):
        return jsonify({"error": "Μη έγκυρη επιλογή επισιτιστικών"}), 400
    try:
        update_employment_catering_override(
            str(ctx["employer_afm"]), str(ctx.get("branch_aa") or "0"), employee_afm,
            catering_override=raw,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"ok": True, "employee_afm": employee_afm, "catering_override": raw})


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
        employment = next((row for row in list_employees_for_employer(
            afm, branch_aa=branch, active_only=False, limit=5000,
        ) if norm_afm(row.get("afm") or "") == employee_afm), {})
        for contract in contracts:
            contract["hire_date"] = employment.get("hire_date")
            contract["departure_date"] = employment.get("departure_date")
            contract["catering_override"] = employment.get("catering_override")
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


@employees_bp.get("/contract/change/draft")
def employment_contract_change_draft():
    """Προσυμπληρωμένη φόρμα WebMA από τρέχουσα σύμβαση + EX_BASE_05."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    employee_afm = norm_afm(request.args.get("employee_afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400

    from app.ergani_client import ErganiClient
    from app.ergani_env import client_for_store
    from app.ergani_parse import extract_raw_list
    from app.http_helpers import ensure_ergani_bearer, json_or_text
    from app.web_ma_payload import (
        CHANGE_TYPES,
        DIEUTHETISI_TYPES,
        IDENTITY_DOCUMENT_TYPES,
        MAIN_INSURANCE_FUNDS,
        SUPPLEMENTARY_INSURANCE_FUNDS,
        draft_from_contract,
        personal_fields_from_ex_base_05,
    )

    contract = None
    try:
        history = list_history_for_employee(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            employee_afm,
            limit=5,
        )
        contract = next(
            (
                row
                for row in history
                if row.get("is_current") in (True, 1, "1")
            ),
            history[0] if history else None,
        )
    except pyodbc.Error as ex:
        return _contract_db_error(ex)

    if not contract:
        employees = list_employees_for_employer(
            str(ctx["employer_afm"]),
            branch_aa=str(ctx.get("branch_aa") or "0"),
            limit=5000,
        )
        emp = next(
            (row for row in employees if norm_afm(row.get("afm") or "") == employee_afm),
            None,
        )
        if not emp:
            return jsonify({"error": "Δεν βρέθηκε εργαζόμενος στο κατάστημα"}), 404
        contract = {
            "employee_afm": employee_afm,
            "eponymo": emp.get("eponymo"),
            "onoma": emp.get("onoma"),
            "branch_aa": ctx.get("branch_aa") or "0",
        }

    merged = dict(contract)
    ergani_enriched = False
    ergani_enrich_error = None
    try:
        from app.wto_submit import clear_ergani_bearer_session, ergani_authorization_denied

        client: ErganiClient = client_for_store(ctx)
        bearer = ensure_ergani_bearer(ctx)
        if not bearer:
            ergani_enrich_error = "Αποτυχία σύνδεσης Ergani API"
        else:
            resp = client.execute_service("EX_BASE_05", [], bearer)
            parsed = json_or_text(resp)
            if ergani_authorization_denied(resp, parsed):
                clear_ergani_bearer_session()
                bearer = ensure_ergani_bearer(ctx)
                if bearer:
                    resp = client.execute_service("EX_BASE_05", [], bearer)
                    parsed = json_or_text(resp)
            if not resp.ok:
                ergani_enrich_error = (
                    (parsed.get("message") if isinstance(parsed, dict) else None)
                    or f"EX_BASE_05 HTTP {resp.status_code}"
                )
            else:
                target_afm = employee_afm
                for item in extract_raw_list(parsed):
                    item_afm = norm_afm(str(item.get("afm") or item.get("Afm") or ""))
                    if item_afm != target_afm:
                        continue
                    personal = personal_fields_from_ex_base_05(item)
                    for key, value in personal.items():
                        if value is None or str(value).strip() == "":
                            continue
                        # Συμπλήρωση κενών + αντικατάσταση προσωπικών από Ergani.
                        if key in (
                            "eponymo",
                            "onoma",
                            "onoma_patros",
                            "onoma_mitros",
                            "birthdate",
                            "sex",
                            "yphkoothta",
                            "typos_taytothtas",
                            "ar_taytothtas",
                            "ekdousa_arxh",
                            "date_ekdosis",
                            "date_ekdosis_lixi",
                            "amka",
                            "amika",
                            "code_anergias",
                            "ar_vivliou_anilikou",
                            "marital_status",
                            "arithmos_teknon",
                            "epipedo_morfosis",
                            "kyria_asfalish",
                            "epikourikiki_kod",
                            "prosthetes_asfalistikes_paroxes",
                            "xronos_katabolhs",
                            "eidos_dieuthethshs",
                            "specialty",
                            "step92",
                            "salary",
                            "hourly_wage",
                            "weekly_hours",
                            "fulltime_contract_weekly_hours",
                            "weekly_work_days",
                            "employment_relation",
                            "regime",
                            "characterization",
                            "prior_service",
                            "break_minutes",
                            "break_in_work",
                            "flex_arrival_minutes",
                            "working_card",
                            "working_time_digital_organization",
                        ) or not str(merged.get(key) or "").strip():
                            merged[key] = value
                    ergani_enriched = True
                    break
                if not ergani_enriched:
                    ergani_enrich_error = (
                        "Ο εργαζόμενος δεν βρέθηκε στην τρέχουσα κατάσταση Ergani (EX_BASE_05)"
                    )
    except Exception as ex:  # noqa: BLE001 — το draft συνεχίζει με τοπικά στοιχεία
        ergani_enriched = False
        ergani_enrich_error = str(ex) or ex.__class__.__name__

    draft = draft_from_contract(
        merged,
        branch_aa=str(ctx.get("branch_aa") or "0"),
        employee_afm=employee_afm,
    )
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "draft": draft,
        "change_types": CHANGE_TYPES,
        "identity_document_types": IDENTITY_DOCUMENT_TYPES,
        "main_insurance_funds": MAIN_INSURANCE_FUNDS,
        "supplementary_insurance_funds": SUPPLEMENTARY_INSURANCE_FUNDS,
        "dieuthetisi_types": DIEUTHETISI_TYPES,
        "ergani_enriched": ergani_enriched,
        "ergani_enrich_error": ergani_enrich_error,
        "available": True,
        "submission_code": draft.get("submission_code"),
    })


@employees_bp.post("/contract/change/submit")
def employment_contract_change_submit():
    """Υποβολή Ψηφιακής Δήλωσης Μεταβολής Στοιχείων Εργασιακής Σχέσης (WebMA)."""
    import base64
    import json as json_lib

    from app.ergani_client import ErganiClient
    from app.ergani_env import client_for_store
    from app.http_helpers import (
        ensure_ergani_bearer,
        json_or_text,
        persist_safe,
        response_body_text,
    )
    from app.web_ma_payload import (
        SUBMISSION_CODE_WEB_MA,
        build_web_ma_payload,
    )
    from app.work_card_payload import WorkCardPayloadError
    from app.wto_submit import (
        ergani_error_message,
        parse_submit_response,
        persist_wto_submit,
        submit_wto_with_auth_retry,
    )

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raw_payload = request.form.get("payload") or request.form.get("data")
        if raw_payload:
            try:
                parsed = json_lib.loads(raw_payload)
            except (TypeError, ValueError, json_lib.JSONDecodeError):
                parsed = None
            data = parsed if isinstance(parsed, dict) else {}
        else:
            data = {}
    else:
        data = dict(data)

    upload = request.files.get("file") or request.files.get("f_file")
    if upload and upload.filename:
        raw = upload.read()
        if not raw:
            return jsonify({"error": "Το επισυναπτόμενο αρχείο είναι κενό"}), 400
        name = str(upload.filename or "").lower()
        if not name.endswith(".pdf"):
            return jsonify({"error": "Το αρχείο πρέπει να είναι PDF"}), 400
        data["f_file"] = base64.b64encode(raw).decode("ascii")

    employee_afm = norm_afm(str(data.get("employee_afm") or ""))
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400

    # Κωδικοί παραρτήματος από το κατάστημα (XSD απαιτεί σειρά πριν το f_eponymo).
    data.setdefault("sepe_code", ctx.get("sepe_code"))
    data.setdefault("oaed_code", ctx.get("oaed_code"))
    data.setdefault("kad_code", ctx.get("kad_code"))
    data.setdefault("kallikratis_code", ctx.get("kallikratis_code"))

    try:
        payload = build_web_ma_payload(
            data,
            branch_aa=str(ctx.get("branch_aa") or "0"),
        )
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400

    client: ErganiClient = client_for_store(ctx)
    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({"error": "Αποτυχία σύνδεσης Ergani API"}), 401

    # Έλεγχος διαθεσιμότητας WebMA στο Lookup/Submissions
    codes_resp = client.submissions_list(bearer)
    codes_parsed = json_or_text(codes_resp)
    codes: list[str] = []
    if isinstance(codes_parsed, list):
        codes = [
            str(item.get("code") or item.get("Code") or "").strip()
            for item in codes_parsed
            if isinstance(item, dict)
        ]
    if codes_resp.ok and codes and SUBMISSION_CODE_WEB_MA not in codes:
        return jsonify({
            "error": "Το Ergani API δεν διαθέτει WebMA για αυτόν τον λογαριασμό",
            "submission_code": SUBMISSION_CODE_WEB_MA,
        }), 400

    resp, parsed, retried = submit_wto_with_auth_retry(
        ctx,
        client,
        SUBMISSION_CODE_WEB_MA,
        payload,
        bearer,
        refresh_bearer=ensure_ergani_bearer,
    )
    body_text = response_body_text(resp)
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    success = bool(resp.ok)
    # Μην γράφουμε το PDF base64 στο sync log.
    persist_payload = payload
    try:
        rows = (payload.get("AnaggeliesMA") or {}).get("AnaggeliaMA") or []
        if rows and isinstance(rows[0], dict) and rows[0].get("f_file"):
            safe_row = dict(rows[0])
            safe_row["f_file"] = f"[pdf {len(str(rows[0].get('f_file')))} chars]"
            persist_payload = {
                "AnaggeliesMA": {"AnaggeliaMA": [safe_row]},
            }
    except Exception:
        persist_payload = {"omitted": True}

    persist_safe(
        lambda: persist_wto_submit(
            SUBMISSION_CODE_WEB_MA,
            str(ctx["employer_afm"]),
            int(resp.status_code),
            success,
            {
                "employee_afm": employee_afm,
                "change_types": data.get("change_types"),
                "change_date": data.get("change_date"),
                "has_file": bool(data.get("f_file")),
                "payload": persist_payload,
            },
            body_text,
            protocol,
            submit_date,
            ergani_id,
        )
    )
    if not success:
        err = ergani_error_message(parsed) or body_text or "Αποτυχία υποβολής WebMA"
        return jsonify({
            "success": False,
            "error": err,
            "status": resp.status_code,
            "submission_code": SUBMISSION_CODE_WEB_MA,
            "response": parsed,
            "retried_auth": retried,
        }), 400

    contract_sync: dict[str, Any] | None = None
    try:
        from app.portal_employment_contract_sync import sync_employment_contracts_from_portal

        contract_sync = sync_employment_contracts_from_portal(
            ctx,
            only_afms={employee_afm},
        )
    except Exception as ex:  # noqa: BLE001 — η υποβολή πέτυχε· το sync είναι best-effort
        contract_sync = {
            "success": False,
            "detail": f"Αποτυχία αυτόματου συγχρονισμού σύμβασης: {ex}",
            "count": 0,
        }

    sync_ok = bool(contract_sync and contract_sync.get("success"))
    message = (
        f"Υποβλήθηκε μεταβολή σύμβασης"
        + (f" · πρωτόκολλο {protocol}" if protocol else "")
    )
    if sync_ok:
        message += " · ενημερώθηκε η λίστα αλλαγών"
    elif contract_sync:
        message += " · ο συγχρονισμός σύμβασης απέτυχε (τρέξτε χειροκίνητα)"

    return jsonify({
        "success": True,
        "submission_code": SUBMISSION_CODE_WEB_MA,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "employee_afm": employee_afm,
        "retried_auth": retried,
        "contract_sync": contract_sync,
        "message": message,
    })


@employees_bp.get("/specialty-catalog")
def employee_specialty_catalog():
    """Τοπικός κατάλογος ειδικοτήτων ΣΤΕΠ'92 (αναζήτηση για autocomplete)."""
    from app import repo_specialty_catalog

    q = (request.args.get("q") or "").strip()
    try:
        lim = int(request.args.get("limit") or "40")
    except ValueError:
        lim = 40

    if not repo_specialty_catalog.table_available() or repo_specialty_catalog.count_rows() == 0:
        # Fallback: live Ergani αν λείπει τοπικός κατάλογος
        from app.ergani_client import ErganiClient
        from app.ergani_env import client_for_store
        from app.ergani_parse import extract_catalog_items, unwrap_ergani_data
        from app.http_helpers import ensure_ergani_bearer, json_or_text

        ctx = resolve_active_store()
        if not ctx:
            return jsonify({
                "error": "Κενός τοπικός κατάλογος ΣΤΕΠ — επιλέξτε κατάστημα ή τρέξτε sync",
                "items": [],
                "source": "empty",
            }), 503
        client: ErganiClient = client_for_store(ctx)
        bearer = ensure_ergani_bearer(ctx)
        if not bearer:
            return jsonify({"error": "Αποτυχία σύνδεσης Ergani API", "items": []}), 401
        params = [{"ParameterName": "Parameter", "ParameterValue": "Step92"}]
        resp = client.execute_service("EX_BASE_03", params, bearer)
        parsed = json_or_text(resp)
        if not resp.ok:
            return jsonify({
                "error": "Αποτυχία φόρτωσης καταλόγου ΣΤΕΠ",
                "status": resp.status_code,
                "items": [],
            }), resp.status_code if resp.status_code >= 400 else 502
        items = extract_catalog_items(unwrap_ergani_data(parsed))
        try:
            repo_specialty_catalog.replace_all(items)
        except Exception:
            pass
        filtered = items
        if q:
            needle = q.casefold()
            filtered = [
                it for it in items
                if needle in str(it.get("value") or "").casefold()
                or needle in str(it.get("description") or "").casefold()
            ]
        return jsonify({
            "catalog": "step92",
            "source": "ergani_live",
            "items": filtered[: max(1, min(lim, 80))],
            "count": len(filtered),
            "total": len(items),
        })

    items = repo_specialty_catalog.search_specialties(q, limit=lim)
    return jsonify({
        "catalog": "step92",
        "source": "local",
        "items": items,
        "count": len(items),
        "total": repo_specialty_catalog.count_rows(),
        "synced_at": repo_specialty_catalog.last_synced_at(),
        "query": q,
    })


@employees_bp.get("/hire/draft")
def employee_hire_draft():
    """Κενή/προεπιλεγμένη φόρμα πρόσληψης (WebE3N) για το ενεργό κατάστημα."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400

    from app.web_e3n_payload import BASICS_ACCEPTANCE_HIRE, empty_hire_draft

    draft = empty_hire_draft(branch_aa=str(ctx.get("branch_aa") or "0"))
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "draft": draft,
        "basics_acceptance_catalog": BASICS_ACCEPTANCE_HIRE,
        "available": True,
        "submission_code": draft.get("submission_code"),
    })


@employees_bp.post("/hire/submit")
def employee_hire_submit():
    """Υποβολή Ψηφιακής Αναγγελίας Έναρξης Εργασίας / Πρόσληψης (WebE3N)."""
    from app.ergani_client import ErganiClient
    from app.ergani_env import client_for_store
    from app.http_helpers import (
        ensure_ergani_bearer,
        json_or_text,
        persist_safe,
        response_body_text,
    )
    from app.web_e3n_payload import SUBMISSION_CODE_WEB_E3N, build_web_e3n_payload
    from app.work_card_payload import WorkCardPayloadError
    from app.wto_submit import (
        ergani_error_message,
        parse_submit_response,
        persist_wto_submit,
        submit_wto_with_auth_retry,
    )

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    data = request.get_json(silent=True) or {}

    try:
        payload = build_web_e3n_payload(
            data,
            branch_aa=str(ctx.get("branch_aa") or "0"),
        )
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400

    employee_afm = norm_afm(str(data.get("employee_afm") or data.get("f_afm") or ""))
    client: ErganiClient = client_for_store(ctx)
    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({"error": "Αποτυχία σύνδεσης Ergani API"}), 401

    codes_resp = client.submissions_list(bearer)
    codes_parsed = json_or_text(codes_resp)
    codes: list[str] = []
    if isinstance(codes_parsed, list):
        codes = [
            str(item.get("code") or item.get("Code") or "").strip()
            for item in codes_parsed
            if isinstance(item, dict)
        ]
    if codes_resp.ok and codes and SUBMISSION_CODE_WEB_E3N not in codes:
        return jsonify({
            "error": "Το Ergani API δεν διαθέτει WebE3N για αυτόν τον λογαριασμό",
            "submission_code": SUBMISSION_CODE_WEB_E3N,
        }), 400

    resp, parsed, retried = submit_wto_with_auth_retry(
        ctx,
        client,
        SUBMISSION_CODE_WEB_E3N,
        payload,
        bearer,
        refresh_bearer=ensure_ergani_bearer,
    )
    body_text = response_body_text(resp)
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    success = bool(resp.ok)
    persist_safe(
        lambda: persist_wto_submit(
            SUBMISSION_CODE_WEB_E3N,
            str(ctx["employer_afm"]),
            int(resp.status_code),
            success,
            {
                "employee_afm": employee_afm,
                "hire_date": data.get("hire_date"),
                "eponymo": data.get("eponymo"),
                "onoma": data.get("onoma"),
                "payload": payload,
            },
            body_text,
            protocol,
            submit_date,
            ergani_id,
        )
    )
    if not success:
        err = ergani_error_message(parsed) or body_text or "Αποτυχία υποβολής WebE3N"
        return jsonify({
            "success": False,
            "error": err,
            "status": resp.status_code,
            "submission_code": SUBMISSION_CODE_WEB_E3N,
            "response": parsed,
            "retried_auth": retried,
        }), 400
    return jsonify({
        "success": True,
        "submission_code": SUBMISSION_CODE_WEB_E3N,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "employee_afm": employee_afm,
        "retried_auth": retried,
        "message": (
            f"Υποβλήθηκε αναγγελία πρόσληψης"
            + (f" · πρωτόκολλο {protocol}" if protocol else "")
        ),
    })
