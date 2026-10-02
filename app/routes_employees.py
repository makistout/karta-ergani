"""API εργαζομένων — λίστα + στοιχεία σύμβασης (Μητρώα)."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

import pyodbc
from flask import Blueprint, jsonify, request

from app.access_control import is_super_admin
from app.http_helpers import resolve_active_store
from app.portal_employment_contract_sync import iter_employment_contract_sync_events
from app.repo_employment_contract import (
    employment_contract_table_missing_message,
    latest_for_employer_employee,
    list_current_for_store,
    list_history_for_employee,
)
from app.repo_entities import (
    get_employee_row_by_afm,
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
from app.repo_employee_leave import load_current_year_normal_leave
from app.repo_work_log import (
    count_incomplete_punches_by_employee_for_month,
    list_work_log_for_range,
    normalize_overnight_work_log_rows,
)

employees_bp = Blueprint("employees", __name__, url_prefix="/api/employees")

EMPLOYEES_STATS_MONTHS_BACK = 6
NO_SPECIALTY_LABEL = "Χωρίς ειδικότητα"


def _shift_month_start(value: date, delta: int) -> date:
    idx = value.year * 12 + (value.month - 1) + int(delta)
    year, month0 = divmod(idx, 12)
    return date(year, month0 + 1, 1)


def _resolve_employees_stats_month(
    *,
    year: Any = None,
    month: Any = None,
    today: date | None = None,
) -> tuple[int, int, date]:
    """Current month, or a past month up to EMPLOYEES_STATS_MONTHS_BACK months back."""
    as_today = today or date.today()
    current = date(as_today.year, as_today.month, 1)
    oldest = _shift_month_start(current, -EMPLOYEES_STATS_MONTHS_BACK)
    if year in (None, "") or month in (None, ""):
        selected = current
    else:
        try:
            selected = date(int(str(year).strip()), int(str(month).strip()), 1)
        except (TypeError, ValueError):
            selected = current
    if selected > current:
        selected = current
    elif selected < oldest:
        selected = oldest
    last_day = calendar.monthrange(selected.year, selected.month)[1]
    as_of = min(as_today, date(selected.year, selected.month, last_day))
    return selected.year, selected.month, as_of


def _resolve_leave_display_month(*, today: date | None = None) -> tuple[int, int, date]:
    """Άδεια από το μηνιαίο αρχείο: τρέχων − 2. Ιαν/Φεβ → Οκτώβριος προηγούμενου."""
    as_today = today or date.today()
    if as_today.month <= 2:
        selected = date(as_today.year - 1, 10, 1)
    else:
        selected = _shift_month_start(date(as_today.year, as_today.month, 1), -2)
    last_day = calendar.monthrange(selected.year, selected.month)[1]
    return selected.year, selected.month, date(selected.year, selected.month, last_day)


def _specialty_label(contract: dict | None) -> str:
    text = str((contract or {}).get("specialty") or "").strip()
    return text or NO_SPECIALTY_LABEL


# Πεδία που το EX_BASE_05 / τρέχουσα σύμβαση μπορούν να προσυμπληρώσουν στο WebMA.
_WEB_MA_ENRICH_KEYS = (
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
    "topos_ergasias",
    "topos_ergasias_comments",
    "efarmostea_sillogiki_simbasi",
    "efarmostea_sillogiki_simbasi_comments",
    "ipoxreotiki_katartisi",
    "mh_problepsimo_programma",
    "trial_period",
    "topothetisioaed",
    "responsible_position",
)


def _optional_iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def _merge_nonempty(base: dict[str, Any], overlay: dict[str, Any], *, keys: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Συμπληρώνει κενά του base από overlay (ή μόνο συγκεκριμένα keys)."""
    out = dict(base)
    items = overlay.items() if keys is None else ((k, overlay.get(k)) for k in keys)
    for key, value in items:
        if value is None:
            continue
        text = str(value).strip()
        if text == "":
            continue
        current = str(out.get(key) or "").strip()
        if not current:
            out[key] = value
    return out


def _load_local_contract_for_web_ma(ctx: dict[str, Any], employee_afm: str) -> dict[str, Any]:
    contract: dict[str, Any] | None = None
    try:
        history = list_history_for_employee(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
            employee_afm,
            limit=5,
        )
        contract = next(
            (row for row in history if row.get("is_current") in (True, 1, "1")),
            history[0] if history else None,
        )
    except pyodbc.Error:
        contract = None
    if contract:
        return dict(contract)
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
        return {"employee_afm": employee_afm, "branch_aa": ctx.get("branch_aa") or "0"}
    return {
        "employee_afm": employee_afm,
        "eponymo": emp.get("eponymo"),
        "onoma": emp.get("onoma"),
        "branch_aa": ctx.get("branch_aa") or "0",
    }


def _fetch_ex_base_05_personal(
    ctx: dict[str, Any], employee_afm: str
) -> tuple[dict[str, Any] | None, str | None]:
    """Επιστρέφει (personal_fields, error)."""
    from app.ergani_client import ErganiClient
    from app.ergani_env import client_for_store
    from app.ergani_parse import extract_raw_list
    from app.http_helpers import ensure_ergani_bearer, json_or_text
    from app.web_ma_payload import personal_fields_from_ex_base_05
    from app.wto_submit import clear_ergani_bearer_session, ergani_authorization_denied

    try:
        client: ErganiClient = client_for_store(ctx)
        bearer = ensure_ergani_bearer(ctx)
        if not bearer:
            return None, "Αποτυχία σύνδεσης Ergani API"
        resp = client.execute_service("EX_BASE_05", [], bearer)
        parsed = json_or_text(resp)
        if ergani_authorization_denied(resp, parsed):
            clear_ergani_bearer_session()
            bearer = ensure_ergani_bearer(ctx)
            if bearer:
                resp = client.execute_service("EX_BASE_05", [], bearer)
                parsed = json_or_text(resp)
        if not resp.ok:
            return None, (
                (parsed.get("message") if isinstance(parsed, dict) else None)
                or f"EX_BASE_05 HTTP {resp.status_code}"
            )
        target = employee_afm
        for item in extract_raw_list(parsed):
            item_afm = norm_afm(str(item.get("afm") or item.get("Afm") or ""))
            if item_afm != target:
                continue
            return personal_fields_from_ex_base_05(item), None
        return None, "Ο εργαζόμενος δεν βρέθηκε στην τρέχουσα κατάσταση Ergani (EX_BASE_05)"
    except Exception as ex:  # noqa: BLE001
        return None, str(ex) or ex.__class__.__name__


def _enrich_web_ma_form_data(
    data: dict[str, Any],
    *,
    ctx: dict[str, Any],
    employee_afm: str,
) -> tuple[dict[str, Any], bool, str | None]:
    """
    Βάση = τοπική σύμβαση + EX_BASE_05 (πρόσληψη/τρέχουσα κατάσταση),
    πάνω της οι μη κενές τιμές της φόρμας.
    """
    merged = _load_local_contract_for_web_ma(ctx, employee_afm)
    personal, err = _fetch_ex_base_05_personal(ctx, employee_afm)
    enriched = False
    if personal:
        merged = _merge_nonempty(merged, personal, keys=_WEB_MA_ENRICH_KEYS)
        # EX_BASE_05 υπερισχύει στα προσωπικά όταν η τοπική σύμβαση τα έχει κενά.
        for key in _WEB_MA_ENRICH_KEYS:
            value = personal.get(key)
            if value is None or str(value).strip() == "":
                continue
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
                "amka",
                "amika",
                "marital_status",
                "arithmos_teknon",
                "epipedo_morfosis",
                "kyria_asfalish",
                "epikourikiki_kod",
                "xronos_katabolhs",
            ) or not str(merged.get(key) or "").strip():
                merged[key] = value
        enriched = True
    # Overlay από φόρμα: ό,τι συμπλήρωσε ο χρήστης κερδίζει.
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            merged[key] = value
            continue
        text = str(value).strip()
        if text != "":
            merged[key] = value
    merged["employee_afm"] = employee_afm
    merged.setdefault("branch_aa", ctx.get("branch_aa") or "0")
    return merged, enriched, err


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
    stats_year, stats_month, stats_as_of = _resolve_employees_stats_month(
        year=request.args.get("year"),
        month=request.args.get("month"),
    )
    open_punches = count_incomplete_punches_by_employee_for_month(
        employer_afm, branch_aa,
        year=stats_year, month=stats_month, store_id=int(ctx["id"]),
    )
    employee_afms = [
        norm_afm(str(row.get("afm") or "")) for row in rows
        if norm_afm(str(row.get("afm") or ""))
    ]
    leave_year, leave_month, leave_as_of = _resolve_leave_display_month()
    try:
        normal_leave = load_current_year_normal_leave(
            store_id=int(ctx["id"]), employee_afms=employee_afms, today=leave_as_of,
        )
    except pyodbc.Error:
        normal_leave = {}
    month_label = f"{stats_month:02d}/{stats_year}"
    leave_label = f"{leave_month:02d}/{leave_year}"
    for row in rows:
        afm = norm_afm(str(row.get("afm") or ""))
        contract = contracts_by_afm.get(afm)
        row["specialty"] = _specialty_label(contract)
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
        "year": stats_year,
        "month": stats_month,
        "open_punches_month_label": month_label,
        "normal_leave_latest_month": leave_label,
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
    employment = next(
        (
            emp for emp in list_employees_for_employer(
                str(ctx["employer_afm"]),
                branch_aa=str(ctx.get("branch_aa") or "0"),
                active_only=False,
                limit=5000,
            )
            if norm_afm(str(emp.get("afm") or "")) == employee_afm
        ),
        None,
    )
    if employment:
        hire = employment.get("hire_date")
        departure = employment.get("departure_date")
        if hasattr(hire, "isoformat"):
            hire = hire.isoformat()
        if hasattr(departure, "isoformat"):
            departure = departure.isoformat()
        for row in rows:
            row["hire_date"] = hire
            row["departure_date"] = departure
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
    if not is_super_admin():
        return jsonify({"error": "Η μεταβολή σύμβασης είναι διαθέσιμη μόνο σε super admin"}), 403
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    employee_afm = norm_afm(request.args.get("employee_afm") or "")
    if not employee_afm:
        return jsonify({"error": "Λείπει employee_afm"}), 400

    from app.web_ma_payload import (
        CHANGE_TYPES,
        DIEUTHETISI_TYPES,
        IDENTITY_DOCUMENT_TYPES,
        MAIN_INSURANCE_FUNDS,
        SUPPLEMENTARY_INSURANCE_FUNDS,
        draft_from_contract,
    )

    merged, ergani_enriched, ergani_enrich_error = _enrich_web_ma_form_data(
        {},
        ctx=ctx,
        employee_afm=employee_afm,
    )
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
    if not is_super_admin():
        return jsonify({"error": "Η μεταβολή σύμβασης είναι διαθέσιμη μόνο σε super admin"}), 403
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

    # Προσυμπλήρωση κενών από σύμβαση πρόσληψης / EX_BASE_05 πριν το build.
    data, _enriched, _enrich_err = _enrich_web_ma_form_data(
        data,
        ctx=ctx,
        employee_afm=employee_afm,
    )

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


def _load_local_hire_history(ctx: dict[str, Any], employee_afm: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        contract = latest_for_employer_employee(str(ctx["employer_afm"]), employee_afm)
    except pyodbc.Error:
        contract = None
    if contract:
        out.update(contract)
    emp = get_employee_row_by_afm(employee_afm)
    if emp:
        for key, src in (
            ("eponymo", "eponymo"),
            ("onoma", "onoma"),
            ("amka", "amka"),
            ("amika", "amika"),
            ("flex_arrival_minutes", "flex_arrival_minutes"),
        ):
            if not str(out.get(key) or "").strip() and emp.get(src):
                out[key] = emp.get(src)
    return out


def _fetch_portal_hire_personal(
    ctx: dict[str, Any], employee_afm: str
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from app.portal_employment_contract_sync import fetch_registry_detail_by_afm

        row = fetch_registry_detail_by_afm(ctx, employee_afm)
        return row, None
    except Exception as ex:  # noqa: BLE001
        return None, str(ex) or ex.__class__.__name__


def _collect_hire_lookup(
    ctx: dict[str, Any],
    employee_afm: str,
) -> tuple[dict[str, Any], list[str], str | None]:
    """Τοπικό αρχείο + Μητρώο portal + EX_BASE_05. Το Εργάνη υπερισχύει."""
    merged: dict[str, Any] = {"employee_afm": employee_afm}
    sources: list[str] = []
    errors: list[str] = []
    local = _load_local_hire_history(ctx, employee_afm)
    if local.get("eponymo") or local.get("onoma") or local.get("salary"):
        merged = _merge_nonempty(merged, local)
        sources.append("local")
    portal, portal_err = _fetch_portal_hire_personal(ctx, employee_afm)
    if portal:
        for key, value in portal.items():
            if value is None or str(value).strip() == "":
                continue
            merged[key] = value
        sources.append("portal")
    elif portal_err:
        errors.append(portal_err)
    personal, ex_err = _fetch_ex_base_05_personal(ctx, employee_afm)
    if personal:
        for key, value in personal.items():
            if value is None or str(value).strip() == "":
                continue
            merged[key] = value
        sources.append("ex_base_05")
    elif ex_err and "δεν βρέθηκε" not in str(ex_err).lower():
        errors.append(ex_err)
    return merged, sources, ("; ".join(errors) if errors else None)


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


@employees_bp.get("/hire/lookup")
def employee_hire_lookup():
    """Αυτόματη συμπλήρωση πρόσληψης από Εργάνη / προηγούμενη απασχόληση."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    employee_afm = norm_afm(
        request.args.get("employee_afm") or request.args.get("afm") or ""
    )
    if len(employee_afm) != 9:
        return jsonify({"error": "Συμπληρώστε έγκυρο ΑΦΜ (9 ψηφία)"}), 400

    from app.web_e3n_payload import BASICS_ACCEPTANCE_HIRE, apply_lookup_to_hire_draft, empty_hire_draft

    merged, sources, err = _collect_hire_lookup(ctx, employee_afm)
    draft = apply_lookup_to_hire_draft(
        empty_hire_draft(branch_aa=str(ctx.get("branch_aa") or "0")),
        merged,
    )
    draft["employee_afm"] = employee_afm
    found = any(
        str(draft.get(key) or "").strip()
        for key in ("eponymo", "onoma", "amka", "ar_taytothtas", "salary", "specialty")
    )
    ergani = "portal" in sources or "ex_base_05" in sources
    if found and ergani:
        message = "Συμπληρώθηκαν τα στοιχεία από το Εργάνη (προηγούμενη απασχόληση)."
    elif found:
        message = "Συμπληρώθηκαν από προηγούμενη απασχόληση στο αρχείο."
    else:
        message = "Δεν βρέθηκε προηγούμενη απασχόληση για αυτό το ΑΦΜ."
    payload = {
        "found": found,
        "draft": draft,
        "sources": sources,
        "message": message,
        "basics_acceptance_catalog": BASICS_ACCEPTANCE_HIRE,
    }
    if err and not found:
        payload["error"] = err
    return jsonify(payload)


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


def _departure_form_data() -> dict[str, Any]:
    import base64
    import json as json_lib

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
            raise ValueError("Το επισυναπτόμενο αρχείο είναι κενό")
        name = str(upload.filename or "").lower()
        if not name.endswith(".pdf"):
            raise ValueError("Το αρχείο πρέπει να είναι PDF")
        data["f_file"] = base64.b64encode(raw).decode("ascii")
    return data


@employees_bp.get("/departure/draft")
def employee_departure_draft():
    """Προσυμπληρωμένη φόρμα ψηφιακής αναγγελίας λήξης εργασίας."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    employee_afm = norm_afm(request.args.get("employee_afm") or request.args.get("afm") or "")
    if len(employee_afm) != 9:
        return jsonify({"error": "Λείπει έγκυρο ΑΦΜ"}), 400

    from app.web_el_payload import apply_contract_to_departure_draft, empty_departure_draft

    draft = empty_departure_draft(branch_aa=str(ctx.get("branch_aa") or "0"))
    draft["employee_afm"] = employee_afm
    merged, enriched, enrich_err = _enrich_web_ma_form_data(
        {"employee_afm": employee_afm},
        ctx=ctx,
        employee_afm=employee_afm,
    )
    merged.setdefault("sepe_code", ctx.get("sepe_code"))
    merged.setdefault("oaed_code", ctx.get("oaed_code"))
    merged.setdefault("kad_code", ctx.get("kad_code"))
    merged.setdefault("kallikratis_code", ctx.get("kallikratis_code"))
    employment = next(
        (
            emp for emp in list_employees_for_employer(
                str(ctx["employer_afm"]),
                branch_aa=str(ctx.get("branch_aa") or "0"),
                active_only=False,
                limit=5000,
            )
            if norm_afm(str(emp.get("afm") or "")) == employee_afm
        ),
        None,
    )
    if employment:
        if employment.get("hire_date"):
            merged["hire_date"] = employment.get("hire_date")
        if employment.get("departure_date") and not merged.get("fixed_term_to"):
            merged["fixed_term_to"] = employment.get("departure_date")
    draft = apply_contract_to_departure_draft(draft, merged)
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "draft": draft,
        "ergani_enriched": enriched,
        "ergani_enrich_error": enrich_err,
    })


@employees_bp.post("/departure/submit")
def employee_departure_submit():
    """Υποβολή Ψηφιακής Αναγγελίας Λήξης Εργασίας στο Ergani API."""
    from app.ergani_client import ErganiClient
    from app.ergani_env import client_for_store
    from app.http_helpers import (
        ensure_ergani_bearer,
        json_or_text,
        persist_safe,
        response_body_text,
    )
    from app.web_el_payload import build_departure_payload, event_date_iso
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
    try:
        data = _departure_form_data()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    employee_afm = norm_afm(str(data.get("employee_afm") or data.get("f_afm") or ""))
    if len(employee_afm) != 9:
        return jsonify({"error": "Λείπει έγκυρο ΑΦΜ εργαζομένου"}), 400
    data, _enriched, _enrich_err = _enrich_web_ma_form_data(
        data, ctx=ctx, employee_afm=employee_afm,
    )
    data.setdefault("sepe_code", ctx.get("sepe_code"))
    data.setdefault("oaed_code", ctx.get("oaed_code"))
    data.setdefault("kad_code", ctx.get("kad_code"))
    data.setdefault("kallikratis_code", ctx.get("kallikratis_code"))

    try:
        submission_code, payload = build_departure_payload(
            data,
            branch_aa=str(ctx.get("branch_aa") or "0"),
        )
    except WorkCardPayloadError as ex:
        return jsonify({"error": str(ex)}), 400

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
    if codes_resp.ok and codes and submission_code not in codes:
        return jsonify({
            "error": f"Το Ergani API δεν διαθέτει {submission_code} για αυτόν τον λογαριασμό",
            "submission_code": submission_code,
        }), 400

    resp, parsed, retried = submit_wto_with_auth_retry(
        ctx,
        client,
        submission_code,
        payload,
        bearer,
        refresh_bearer=ensure_ergani_bearer,
    )
    body_text = response_body_text(resp)
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    success = bool(resp.ok)
    persist_safe(
        lambda: persist_wto_submit(
            submission_code,
            str(ctx["employer_afm"]),
            int(resp.status_code),
            success,
            {
                "employee_afm": employee_afm,
                "event_date": data.get("event_date"),
                "eponymo": data.get("eponymo"),
                "onoma": data.get("onoma"),
                "payload": _departure_payload_for_log(payload),
            },
            body_text,
            protocol,
            submit_date,
            ergani_id,
        )
    )
    if not success:
        err = ergani_error_message(parsed) or body_text or "Αποτυχία υποβολής λήξης εργασίας"
        return jsonify({
            "success": False,
            "error": err,
            "status": resp.status_code,
            "submission_code": submission_code,
            "response": parsed,
            "retried_auth": retried,
        }), 400

    departure_iso = event_date_iso(data, submission_code)
    hire_iso = _hire_iso_from_form(data.get("hire_date"))
    if departure_iso and hire_iso:
        try:
            update_employment_dates(
                str(ctx["employer_afm"]),
                str(ctx.get("branch_aa") or "0"),
                employee_afm,
                hire_date=_optional_iso_date(hire_iso),
                departure_date=_optional_iso_date(departure_iso),
            )
        except Exception:
            pass
    return jsonify({
        "success": True,
        "submission_code": submission_code,
        "protocol": protocol,
        "submit_date": submit_date,
        "ergani_submission_id": ergani_id,
        "employee_afm": employee_afm,
        "departure_date": departure_iso,
        "retried_auth": retried,
        "message": (
            f"Υποβλήθηκε αναγγελία λήξης εργασίας"
            + (f" · πρωτόκολλο {protocol}" if protocol else "")
        ),
    })


def _departure_payload_for_log(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for wrapper, body in payload.items():
        if not isinstance(body, dict):
            out[wrapper] = body
            continue
        cloned: dict[str, Any] = {}
        for key, rows in body.items():
            if not isinstance(rows, list):
                cloned[key] = rows
                continue
            cloned[key] = [
                {name: ("[pdf]" if name.endswith("_file") or name == "f_file" else value)
                 for name, value in row.items()}
                if isinstance(row, dict) else row
                for row in rows
            ]
        out[wrapper] = cloned
    return out


def _hire_iso_from_form(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    if "/" in text:
        parts = text.replace(".", "/").split("/")
        if len(parts) == 3:
            day, month, year = parts
            return f"{year.zfill(4)}-{month.zfill(2)}-{day.zfill(2)}"
    return ""
