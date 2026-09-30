"""API μισθοδοσίας α’ φάσης: παράμετροι και μεικτά από ωρομέτρηση."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any

from flask import Blueprint, current_app, jsonify, request, send_file, session

from app.http_helpers import resolve_active_store
from app.office_auth import SESSION_USER
from app.payroll import (
    catalog_groups,
    PARAMETER_CATALOG,
    attach_apd_identity,
    build_payroll_report,
    payroll_afm_key,
)
from app.payroll_export import build_payroll_export_xlsx
from app.payroll_adjustments import apply_payroll_adjustments
from app.repo_employment_contract import list_current_for_store, list_history_for_store
from app.repo_entities import list_employees_for_employer
from app.repo_schedule import list_schedule_for_range
from app import repo_store
from app.repo_payroll import (
    DB_SETUP,
    ensure_seeded,
    load_resolved,
    public_parameter_rows,
    save_parameters,
    table_missing_message,
    tables_available,
)
from app.routes_apologistic import (
    TimekeepingPeriodError,
    _build_timekeeping_for_month,
    _build_timekeeping_for_week,
)

payroll_bp = Blueprint("payroll", __name__, url_prefix="/api/payroll")


def _as_of_from_body(body: dict) -> date:
    raw = str(body.get("valid_from") or body.get("as_of") or "").strip()[:10]
    if raw:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    if body.get("year") and body.get("month"):
        year = int(body["year"])
        month = int(body["month"])
        return date(year, month, monthrange(year, month)[1])
    week = str(body.get("week_from") or "").strip()[:10]
    if week:
        start = datetime.strptime(week, "%Y-%m-%d").date()
        return start
    return date.today()


def _missing_table():
    return jsonify({
        "error": "Λείπει ο πίνακας παραμέτρων μισθοδοσίας",
        "db_setup": DB_SETUP,
    }), 503


@payroll_bp.get("/catalog")
def payroll_catalog():
    return jsonify({
        "groups": catalog_groups(),
        "parameters": [
            {key: item[key] for key in item if key != "choices"} | (
                {"choices": list(item["choices"])} if item.get("choices") else {}
            )
            for item in PARAMETER_CATALOG
        ],
    })


@payroll_bp.get("/parameters")
def payroll_parameters_get():
    if not tables_available():
        return _missing_table()
    ensure_seeded()
    store_id = int(request.args.get("store_id") or 0)
    as_of = _as_of_from_body({"as_of": request.args.get("as_of")})
    rows = public_parameter_rows(store_id)
    return jsonify({
        "store_id": store_id,
        "as_of": as_of.isoformat(),
        "resolved": load_resolved(store_id=store_id, as_of=as_of),
        "rows": rows,
        "groups": catalog_groups(),
        "catalog": [
            {**item, "choices": list(item["choices"])} if item.get("choices") else dict(item)
            for item in PARAMETER_CATALOG
        ],
    })


@payroll_bp.put("/parameters")
def payroll_parameters_put():
    if not tables_available():
        return _missing_table()
    body = request.get_json(silent=True) or {}
    store_id = int(body.get("store_id") or 0)
    valid_from = _as_of_from_body(body)
    items = body.get("items") or body.get("parameters") or []
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Στείλτε λίστα παραμέτρων"}), 400
    try:
        rows = save_parameters(
            items,
            store_id=store_id,
            valid_from=valid_from,
            updated_by=str(session.get(SESSION_USER) or "")[:100],
        )
    except LookupError:
        return _missing_table()
    except Exception as exc:
        msg = table_missing_message(exc)
        if msg:
            return jsonify({"error": msg, "db_setup": DB_SETUP}), 503
        raise
    return jsonify({
        "success": True,
        "store_id": store_id,
        "valid_from": valid_from.isoformat(),
        "resolved": load_resolved(store_id=store_id, as_of=valid_from),
        "rows": rows,
    })


def _payroll_period_error(exc: Exception):
    if isinstance(exc, LookupError):
        return jsonify({"error": str(exc)}), 404
    if isinstance(exc, TimekeepingPeriodError):
        return jsonify({"error": str(exc), "problem_weeks": exc.problem_weeks}), 409
    status = 409 if "Σ ή Μ" in str(exc) else 400
    return jsonify({"error": str(exc)}), status


def _contracts_by_afm(ctx: dict[str, Any]) -> dict[str, dict]:
    contracts = list_current_for_store(str(ctx["employer_afm"]), str(ctx.get("branch_aa") or "0"))
    by_afm: dict[str, dict] = {}
    for row in contracts:
        key = payroll_afm_key(row.get("employee_afm"))
        if key:
            by_afm[key] = dict(row)
    try:
        for emp in list_employees_for_employer(
            str(ctx["employer_afm"]),
            branch_aa=str(ctx.get("branch_aa") or "0"),
            active_only=False,
        ):
            afm = payroll_afm_key(emp.get("afm"))
            row = by_afm.get(afm)
            if not row:
                continue
            if emp.get("hire_date") and not row.get("hire_date"):
                row["hire_date"] = emp.get("hire_date")
            if emp.get("departure_date") and not row.get("departure_date"):
                row["departure_date"] = emp.get("departure_date")
    except Exception as ex:
        current_app.logger.exception("payroll hire_date merge: %s", ex)
    return by_afm


def _build_payroll_for_body(ctx: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    if "adjustments" in body and body.get("store_id") != int(ctx["id"]):
        raise ValueError("Το ενεργό κατάστημα άλλαξε. Ανανεώστε τη μισθοδοσία")
    if body.get("year") is not None or body.get("month") is not None:
        year = int(body.get("year") or 0)
        month = int(body.get("month") or 0)
        result, snapshots, _annual = _build_timekeeping_for_month(ctx, year=year, month=month)
        period_type = "month"
        period_from = date(year, month, 1)
        period_to = date(year, month, monthrange(year, month)[1])
        extra = {
            "year": year,
            "month": month,
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
            "source_runs": snapshots,
        }
        as_of = period_to
        filename_tag = f"month_{year}{month:02d}"
    else:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        if week_from.weekday() != 0:
            raise ValueError("Η εβδομάδα πρέπει να ξεκινά Δευτέρα")
        result, snapshot, _annual = _build_timekeeping_for_week(ctx, week_from)
        period_type = "week"
        extra = {
            "week_from": week_from.isoformat(),
            "week_to": (week_from + timedelta(days=6)).isoformat(),
            "source_run": snapshot,
        }
        as_of = week_from
        period_from = week_from
        period_to = week_from + timedelta(days=6)
        filename_tag = f"week_{week_from.isoformat().replace('-', '')}"
    params = load_resolved(store_id=int(ctx["id"]), as_of=as_of)
    history = list_history_for_store(str(ctx["employer_afm"]), str(ctx.get("branch_aa") or "0"), limit=50000)
    if len(history) >= 50000:
        raise ValueError("Το ιστορικό συμβάσεων υπερβαίνει το όριο ανάγνωσης μισθοδοσίας")
    schedule_rows = None
    if period_type in ("month", "week"):
        dates = [(period_from + timedelta(days=i)).strftime("%d/%m/%Y")
                 for i in range((period_to - period_from).days + 1)]
        employer, branch = str(ctx["employer_afm"]), str(ctx.get("branch_aa") or "0")
        schedule_rows = list_schedule_for_range(employer, branch, dates, limit=20000)
        if len(schedule_rows) >= 20000:
            # Do not silently prorate using a truncated result.
            schedule_rows = []
            for work_date in dates:
                rows = list_schedule_for_range(employer, branch, [work_date], limit=20000)
                if len(rows) >= 20000:
                    raise ValueError("Το δηλωμένο πρόγραμμα υπερβαίνει το όριο ανάγνωσης μισθοδοσίας")
                schedule_rows.extend(rows)
    payroll = build_payroll_report(
        result, _contracts_by_afm(ctx), params, period_type=period_type,
        period_from=period_from, period_to=period_to,
        schedule_rows=schedule_rows,
        contract_history=history,
    )
    if "adjustments" in body:
        payroll = apply_payroll_adjustments(payroll, body["adjustments"])
    employees_by_afm = {
        payroll_afm_key(emp.get("afm")): emp
        for emp in list_employees_for_employer(
            str(ctx["employer_afm"]),
            branch_aa=str(ctx.get("branch_aa") or "0"),
            active_only=False,
        )
        if payroll_afm_key(emp.get("afm"))
    }
    attach_apd_identity(
        payroll,
        store=repo_store.get_store_config(int(ctx["id"])) or dict(ctx),
        employees_by_afm=employees_by_afm,
        timekeeping=result,
    )
    return {
        "payroll": payroll,
        "result": result,
        "extra": extra,
        "period_from": period_from,
        "period_to": period_to,
        "filename_tag": filename_tag,
    }


@payroll_bp.post("/calculate")
def payroll_calculate():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    if not tables_available():
        return _missing_table()
    ensure_seeded()
    body = request.get_json(silent=True) or {}
    try:
        built = _build_payroll_for_body(ctx, body)
    except LookupError as exc:
        return _payroll_period_error(exc)
    except TimekeepingPeriodError as exc:
        return _payroll_period_error(exc)
    except ValueError as exc:
        return _payroll_period_error(exc)
    payroll = built["payroll"]
    result = built["result"]
    return jsonify({
        **payroll,
        "store": {"id": ctx["id"], "name": ctx["name"]},
        "timekeeping_version": result.get("calculation_version"),
        "timekeeping_counts": result.get("counts"),
        **built["extra"],
    })


@payroll_bp.post("/export")
def payroll_export():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    if not tables_available():
        return _missing_table()
    ensure_seeded()
    body = request.get_json(silent=True) or {}
    try:
        built = _build_payroll_for_body(ctx, body)
    except LookupError as exc:
        return _payroll_period_error(exc)
    except TimekeepingPeriodError as exc:
        return _payroll_period_error(exc)
    except ValueError as exc:
        return _payroll_period_error(exc)
    period_from = built["period_from"]
    period_to = built["period_to"]
    payroll = built["payroll"]
    if body.get("format") == "apd-preview":
        return jsonify({"employees": payroll["employees"], "apd_xml": payroll["apd_xml"]})
    content = build_payroll_export_xlsx(
        report=payroll,
        store={
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
        },
        meta_line=(
            f"{ctx['name']} · {period_from:%d/%m/%Y}–{period_to:%d/%m/%Y} · "
            f"{payroll.get('calculation_version')}"
        ),
    )
    return send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"misthodosia_{built['filename_tag']}.xlsx",
    )
