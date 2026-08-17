"""API for the previous-week retrospective work-time report."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, jsonify, request, session

from app.apologistic import previous_week
from app.apologistic_export import build_apologistic_export_xlsx
from app.apologistic_submit import (
    load_apologistic_day_row,
    overtime_submit_group_from_row,
    schedule_body_from_apologistic_row,
)
from app.date_util import iso_to_ergani_dates
from app.http_helpers import resolve_active_store
from app.office_auth import SESSION_USER
from app.repo_apologistic import (
    apply_exchange, accept_all_review, accept_review, accept_uneven_distribution_group,
    load_report, record_ergani_submit,
    enrich_employee_month_days, list_store_days, successful_overtime_minutes_for_year,
    tables_available, update_proposed,
)
from app.routes_wto_apologistic import execute_apologistic_wto_submit, json_submit_result
from app.wto_submit import parse_submit_response
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY_A, build_wto_daily_a_payload
from app.wto_ov_payload import SUBMISSION_CODE_WTO_OV_A, build_wto_ov_a_payload
from app.work_card_payload import WorkCardPayloadError


apologistic_bp = Blueprint("apologistic", __name__, url_prefix="/api/apologistic")


def _saved_range_response(ctx: dict, date_from: date, date_to: date):
    days = list_store_days(store_id=int(ctx["id"]), date_from=date_from, date_to=date_to)
    enrich_employee_month_days(
        store_id=int(ctx["id"]), employer_afm=str(ctx["employer_afm"]),
        branch_aa=str(ctx.get("branch_aa") or "0"), days=days,
    )
    employees = sorted({str(row.get("employee_afm") or "") for row in days if row.get("employee_afm")})
    work_dates = sorted({str(row.get("work_date") or "") for row in days}, key=lambda value: datetime.strptime(value, "%d/%m/%Y"))
    return {
        "store": {"id": ctx["id"], "name": ctx["name"], "employer_afm": ctx["employer_afm"],
                  "branch_aa": ctx["branch_aa"]},
        "from": date_from.isoformat(), "to": date_to.isoformat(), "work_dates": work_dates,
        "employees": employees, "days": days,
        "legal_notice": "Ελεγκτικό προσχέδιο από αποθηκευμένα αποτελέσματα. Οι εγγραφές «Έλεγχος» δεν αποτελούν αυτόματη δήλωση.",
    }


@apologistic_bp.get("/range")
def apologistic_range():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    try:
        date_from = datetime.strptime(str(request.args.get("from") or "")[:10], "%Y-%m-%d").date()
        date_to = datetime.strptime(str(request.args.get("to") or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Μη έγκυρο διάστημα"}), 400
    if date_to < date_from:
        return jsonify({"error": "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη"}), 400
    if (date_to - date_from).days > 366:
        return jsonify({"error": "Το διάστημα δεν μπορεί να υπερβαίνει το ένα έτος"}), 400
    _, latest_completed_to = previous_week()
    if date_to > latest_completed_to:
        return jsonify({"error": "Το διάστημα μπορεί να φτάνει έως την τελευταία ολοκληρωμένη εβδομάδα"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503
    return jsonify(_saved_range_response(ctx, date_from, date_to))


@apologistic_bp.get("/month")
def apologistic_month():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    today = date.today()
    try:
        year = int(request.args.get("year") or today.year)
        month = int(request.args.get("month") or today.month)
        month_from = date(year, month, 1)
        month_to = date(year, month, monthrange(year, month)[1])
    except (TypeError, ValueError):
        return jsonify({"error": "Μη έγκυρος μήνας"}), 400
    if month_from > date(today.year, today.month, 1):
        return jsonify({"error": "Οι επόμενοι μήνες δεν είναι διαθέσιμοι στο απολογιστικό"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503

    payload = _saved_range_response(ctx, month_from, month_to)
    days = payload["days"]
    first_monday = month_from - timedelta(days=month_from.weekday())
    latest_completed, _ = previous_week()
    weeks = []
    cursor_week = first_monday
    saved_weeks = {str(row.get("week_from") or "")[:10] for row in days}
    while cursor_week <= month_to:
        week_to = cursor_week + timedelta(days=6)
        weeks.append({
            "from": cursor_week.isoformat(), "to": week_to.isoformat(),
            "visible_from": max(cursor_week, month_from).isoformat(),
            "visible_to": min(week_to, month_to).isoformat(),
            "available": cursor_week <= latest_completed and cursor_week.isoformat() in saved_weeks,
        })
        cursor_week += timedelta(days=7)
    return jsonify({**payload,
        "year": year, "month": month, "from": month_from.isoformat(), "to": month_to.isoformat(),
        "weeks": weeks,
    })


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


@apologistic_bp.put("/accept-review")
def apologistic_accept_review():
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
        result = accept_review(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            work_date=work_date, changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/exchange")
def apologistic_apply_exchange():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        rest_work_date = datetime.strptime(str(body.get("rest_work_date") or ""), "%d/%m/%Y").date()
        replacement_work_date = datetime.strptime(
            str(body.get("replacement_work_date") or ""), "%d/%m/%Y"
        ).date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = apply_exchange(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            rest_work_date=rest_work_date, replacement_work_date=replacement_work_date,
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/uneven-distribution/accept")
def apologistic_accept_uneven_distribution():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        employee_afm = str(body.get("employee_afm") or "").strip()
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        result = accept_uneven_distribution_group(
            store_id=int(ctx["id"]), week_from=week_from, employee_afm=employee_afm,
            group_id=str(body.get("group_id") or ""),
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.put("/accept-all-review")
def apologistic_accept_all_review():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True) or {}
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Δεν υπάρχουν εγγραφές για έγκριση"}), 400
    try:
        week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
        result = accept_all_review(
            store_id=int(ctx["id"]),
            week_from=week_from,
            items=items,
            changed_by=str(session.get(SESSION_USER) or "").strip() or None,
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify({"success": True, **result})


@apologistic_bp.post("/export")
def apologistic_export():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503
    body = request.get_json(silent=True) or {}
    headers = body.get("headers") or []
    rows = body.get("rows") or []
    if not isinstance(headers, list) or not isinstance(rows, list):
        return jsonify({"error": "Μη έγκυρα δεδομένα εξαγωγής"}), 400
    if not headers or not rows:
        return jsonify({"error": "Δεν υπάρχουν αποτελέσματα για εξαγωγή"}), 400
    store_name = str(body.get("store_name") or ctx.get("name") or "").strip()
    period_label = str(body.get("period_label") or "").strip()
    filter_label = str(body.get("filter_label") or "").strip()
    meta_parts = [part for part in (store_name, period_label, filter_label) if part]
    meta_line = " · ".join(meta_parts) if meta_parts else "Απολογιστικό εβδομάδας"
    try:
        content = build_apologistic_export_xlsx(meta_line=meta_line, headers=headers, rows=rows)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    week_from = str(body.get("week_from") or "")[:10].replace("-", "")
    filename = f"apologistic_{week_from or 'week'}.xlsx"
    return Response(
        content,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _parse_apologistic_lookup(body: dict) -> tuple[datetime.date, datetime.date, str]:
    week_from = datetime.strptime(str(body.get("week_from") or "")[:10], "%Y-%m-%d").date()
    work_date = datetime.strptime(str(body.get("work_date") or ""), "%d/%m/%Y").date()
    employee_afm = str(body.get("employee_afm") or "").strip()
    if len(employee_afm) != 9 or not employee_afm.isdigit():
        raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
    return week_from, work_date, employee_afm


def _persist_apologistic_submit(
    ctx: dict[str, Any],
    body: dict[str, Any],
    *,
    submission_code: str,
    resp,
    parsed,
    declaration_id: int | None,
    proposed_at_submit: str | None = None,
    segment_reference_date=None,
) -> dict[str, Any] | None:
    if not resp.ok:
        return None
    try:
        week_from, work_date, employee_afm = _parse_apologistic_lookup(body)
    except ValueError:
        return None
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    return record_ergani_submit(
        store_id=int(ctx["id"]),
        week_from=week_from,
        employee_afm=employee_afm,
        work_date=work_date,
        submission_code=submission_code,
        declaration_id=declaration_id,
        success=True,
        protocol=protocol,
        ergani_submission_id=ergani_id,
        submit_date_text=submit_date,
        proposed_at_submit=proposed_at_submit,
        segment_reference_date=segment_reference_date,
        submitted_by=str(session.get(SESSION_USER) or "").strip() or None,
    )


@apologistic_bp.post("/submit-schedule")
def apologistic_submit_schedule():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503

    try:
        if body.get("use_snapshot", True):
            week_from, work_date, employee_afm = _parse_apologistic_lookup(body)
            row = load_apologistic_day_row(
                store_id=int(ctx["id"]),
                week_from=week_from,
                employee_afm=employee_afm,
                work_date=work_date,
            )
            schedule_body = schedule_body_from_apologistic_row(row)
        else:
            schedule_body = body
        payload = build_wto_daily_a_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=str(schedule_body["employee_afm"]),
            employee_last_name=str(schedule_body["eponymo"]),
            employee_first_name=str(schedule_body["onoma"]),
            reference_date=str(schedule_body["reference_date"]),
            schedule_type=str(schedule_body.get("schedule_type") or "ΕΡΓ"),
            hour_from=schedule_body.get("hour_from"),
            hour_to=schedule_body.get("hour_to"),
            intervals=schedule_body.get("intervals") if isinstance(schedule_body.get("intervals"), list) else None,
            comments=body.get("comments"),
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except WorkCardPayloadError as exc:
        return jsonify({"error": str(exc)}), 400

    resp, parsed, auth_retry, declaration_id = execute_apologistic_wto_submit(
        ctx,
        submission_code=SUBMISSION_CODE_WTO_DAILY_A,
        payload=payload,
        audit_action="apologistic.submit_schedule",
        employee_afm=str(schedule_body["employee_afm"]),
        reference_date=str(schedule_body["reference_date"]),
        audit_details={
            "source": "apologistic",
            "proposed": schedule_body.get("proposed"),
            "week_from": str(body.get("week_from") or "")[:10] or None,
            "work_date": str(body.get("work_date") or "").strip() or None,
        },
    )
    if resp is None:
        return jsonify(parsed), 401
    ergani_submit = _persist_apologistic_submit(
        ctx,
        body,
        submission_code=SUBMISSION_CODE_WTO_DAILY_A,
        resp=resp,
        parsed=parsed,
        declaration_id=declaration_id,
        proposed_at_submit=str(schedule_body.get("proposed") or "").strip() or None,
    )
    return json_submit_result(
        submission_code=SUBMISSION_CODE_WTO_DAILY_A,
        resp=resp,
        parsed=parsed,
        auth_retry=auth_retry,
        extra={"ergani_submit": ergani_submit} if ergani_submit else None,
    )


@apologistic_bp.post("/submit-overtime")
def apologistic_submit_overtime():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Αναμενόταν JSON"}), 400
    if not tables_available():
        return jsonify({"error": "Δεν έχουν εγκατασταθεί οι πίνακες απολογιστικού"}), 503

    try:
        if body.get("use_snapshot", True):
            week_from, work_date, employee_afm = _parse_apologistic_lookup(body)
            row = load_apologistic_day_row(
                store_id=int(ctx["id"]),
                week_from=week_from,
                employee_afm=employee_afm,
                work_date=work_date,
            )
            reference_date, day_segments = overtime_submit_group_from_row(
                row,
                segment_date_ergani=str(body.get("segment_date") or "").strip() or None,
            )
            submit_body = {
                "employee_afm": row.get("employee_afm"),
                "eponymo": row.get("eponymo"),
                "onoma": row.get("onoma"),
                "reference_date": reference_date,
                "intervals": [{"hour_from": s["hour_from"], "hour_to": s["hour_to"]} for s in day_segments],
            }
        else:
            submit_body = body
        payload = build_wto_ov_a_payload(
            branch_aa=str(ctx.get("branch_aa") or "0"),
            employee_afm=str(submit_body["employee_afm"]),
            employee_last_name=str(submit_body["eponymo"]),
            employee_first_name=str(submit_body["onoma"]),
            reference_date=str(submit_body["reference_date"]),
            hour_from=submit_body.get("hour_from"),
            hour_to=submit_body.get("hour_to"),
            intervals=submit_body.get("intervals") if isinstance(submit_body.get("intervals"), list) else None,
            comments=body.get("comments"),
        )
    except (ValueError, LookupError) as exc:
        return jsonify({"error": str(exc)}), 400
    except WorkCardPayloadError as exc:
        return jsonify({"error": str(exc)}), 400

    reference_year = datetime.strptime(str(submit_body["reference_date"])[:10], "%Y-%m-%d").year
    submitted_minutes = successful_overtime_minutes_for_year(
        store_id=int(ctx["id"]), employee_afm=str(submit_body["employee_afm"]), year=reference_year,
    )
    new_minutes = 0
    for interval in submit_body.get("intervals") or [{"hour_from": submit_body.get("hour_from"), "hour_to": submit_body.get("hour_to")}]:
        start = datetime.strptime(str(interval.get("hour_from") or ""), "%H:%M")
        end = datetime.strptime(str(interval.get("hour_to") or ""), "%H:%M")
        minutes = int((end - start).total_seconds() // 60)
        new_minutes += minutes + (1440 if minutes < 0 else 0)
    projected_minutes = submitted_minutes + new_minutes
    if projected_minutes > 150 * 60 and not body.get("confirm_annual_limit"):
        return jsonify({
            "error": (
                f"Με τη νέα υποβολή οι επιτυχώς υποβλημένες υπερωρίες του {reference_year} "
                f"θα φτάσουν {projected_minutes // 60}:{projected_minutes % 60:02d}, πάνω από το όριο των 150 ωρών."
            ),
            "requires_confirmation": True,
            "annual_submitted_minutes": submitted_minutes,
            "new_overtime_minutes": new_minutes,
            "projected_annual_minutes": projected_minutes,
        }), 409

    resp, parsed, auth_retry, declaration_id = execute_apologistic_wto_submit(
        ctx,
        submission_code=SUBMISSION_CODE_WTO_OV_A,
        payload=payload,
        audit_action="apologistic.submit_overtime",
        employee_afm=str(submit_body["employee_afm"]),
        reference_date=str(submit_body["reference_date"]),
        audit_details={
            "source": "apologistic",
            "week_from": str(body.get("week_from") or "")[:10] or None,
            "work_date": str(body.get("work_date") or "").strip() or None,
            "segment_count": len(submit_body.get("intervals") or []) or (1 if submit_body.get("hour_from") else 0),
        },
    )
    if resp is None:
        return jsonify(parsed), 401
    segment_reference_date = None
    try:
        segment_reference_date = datetime.strptime(str(submit_body["reference_date"])[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    ergani_submit = _persist_apologistic_submit(
        ctx,
        body,
        submission_code=SUBMISSION_CODE_WTO_OV_A,
        resp=resp,
        parsed=parsed,
        declaration_id=declaration_id,
        segment_reference_date=segment_reference_date,
    )
    return json_submit_result(
        submission_code=SUBMISSION_CODE_WTO_OV_A,
        resp=resp,
        parsed=parsed,
        auth_retry=auth_retry,
        extra={"ergani_submit": ergani_submit} if ergani_submit else None,
    )
