"""Φόρμα ημερήσιου ωραρίου (HTML) — ίδια λογική με Excel import."""

from __future__ import annotations

from typing import Any

from flask import current_app

from app.date_util import format_date_for_ergani
from app.ergani_client import ErganiClient
from app.http_helpers import ensure_ergani_bearer
from app.repo_entities import list_employees_for_employer
from app.repo_schedule import list_schedule_for_store
from app.schedule_excel_import import (
    _build_import_row,
    _build_intervals,
    _current_snapshot_for_employee,
    _hm_short,
    _schedule_is_rest,
    _validate_proposed_row,
    format_snapshot_label,
    summarize_import_rows,
)
from app.schedule_import_service import apply_import_row
from app.schedule_sync import fetch_and_save_schedule_for_ctx
from app.work_card_payload import norm_afm


def _snapshot_to_form_fields(snapshot: list[dict[str, Any]]) -> dict[str, str]:
    if not snapshot:
        return {
            "energia": "",
            "hour_from_1": "",
            "hour_to_1": "",
            "hour_from_2": "",
            "hour_to_2": "",
        }
    if any(
        str(item.get("schedule_type") or item.get("shift_type") or "").strip().upper() in ("ΑΝ", "AN")
        or _schedule_is_rest(item)
        for item in snapshot
    ):
        return {
            "energia": "REPO",
            "hour_from_1": "",
            "hour_to_1": "",
            "hour_from_2": "",
            "hour_to_2": "",
        }
    hf1 = ht1 = hf2 = ht2 = ""
    work_items = [
        item for item in snapshot
        if _hm_short(str(item.get("hour_from") or "")) or _hm_short(str(item.get("hour_to") or ""))
    ]
    if len(work_items) > 0:
        hf1 = _hm_short(str(work_items[0].get("hour_from") or ""))
        ht1 = _hm_short(str(work_items[0].get("hour_to") or ""))
    if len(work_items) > 1:
        hf2 = _hm_short(str(work_items[1].get("hour_from") or ""))
        ht2 = _hm_short(str(work_items[1].get("hour_to") or ""))
    return {
        "energia": "WORK" if (hf1 or ht1) else "",
        "hour_from_1": hf1,
        "hour_to_1": ht1,
        "hour_from_2": hf2,
        "hour_to_2": ht2,
    }


def _parse_form_row(row: dict[str, Any]) -> tuple[str, list[dict[str, str]], str | None, list[str]]:
    energia = str(row.get("energia") or "").strip().upper()
    hf1 = _hm_short(str(row.get("hour_from_1") or ""))
    ht1 = _hm_short(str(row.get("hour_to_1") or ""))
    hf2 = _hm_short(str(row.get("hour_from_2") or ""))
    ht2 = _hm_short(str(row.get("hour_to_2") or ""))

    if energia in ("REPO", "ΡΕΠΟ", "ΑΝ"):
        return "rest", [], None, []
    if energia not in ("WORK", "ΕΡΓ") and not (hf1 or ht1 or hf2 or ht2):
        return "skip", [], None, []
    intervals = _build_intervals(hf1, ht1, hf2, ht2)
    errors = _validate_proposed_row(import_action="work", intervals=intervals)
    return "work", intervals, "ΕΡΓ", errors


def build_day_form(ctx: dict[str, Any], *, date_iso: str) -> dict[str, Any]:
    from app.repo_card import list_card_events_for_store_date
    from app.repo_work_log import list_work_log_for_store

    work_date = format_date_for_ergani(date_iso)
    iso = str(date_iso or "").strip()[:10]
    employer_afm = str(ctx["employer_afm"])
    branch_aa = str(ctx.get("branch_aa") or "0")
    employees = list_employees_for_employer(employer_afm, branch_aa)
    current_schedule = list_schedule_for_store(employer_afm, branch_aa, work_date)

    punched_afms: set[str] = set()
    try:
        for wl in list_work_log_for_store(employer_afm, branch_aa, work_date):
            afm = norm_afm(str(wl.get("employee_afm") or ""))
            if not afm:
                continue
            if str(wl.get("hour_from") or "").strip() or str(wl.get("hour_to") or "").strip():
                punched_afms.add(afm)
    except Exception:
        current_app.logger.exception("day-form work_log lookup failed")
    try:
        for ev in list_card_events_for_store_date(employer_afm, branch_aa, iso):
            afm = norm_afm(str(ev.get("f_afm") or ""))
            if afm:
                punched_afms.add(afm)
    except Exception:
        current_app.logger.exception("day-form card_event lookup failed")

    rows: list[dict[str, Any]] = []
    for emp in employees:
        afm = norm_afm(str(emp.get("afm") or ""))
        if not afm:
            continue
        snapshot = _current_snapshot_for_employee(current_schedule, afm)
        fields = _snapshot_to_form_fields(snapshot)
        rows.append({
            "employee_afm": afm,
            "eponymo": str(emp.get("eponymo") or "").strip(),
            "onoma": str(emp.get("onoma") or "").strip(),
            "current_label": format_snapshot_label(snapshot),
            "has_card_punch": afm in punched_afms,
            **fields,
        })

    rows.sort(key=lambda r: (
        (r.get("eponymo") or "").upper(),
        (r.get("onoma") or "").upper(),
        r.get("employee_afm") or "",
    ))
    return {
        "work_date": work_date,
        "date_iso": iso,
        "rows": rows,
    }


def preview_day_form(
    ctx: dict[str, Any],
    *,
    date_iso: str,
    form_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    work_date = format_date_for_ergani(date_iso)
    employer_afm = str(ctx["employer_afm"])
    branch_aa = str(ctx.get("branch_aa") or "0")
    current_schedule = list_schedule_for_store(employer_afm, branch_aa, work_date)

    import_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(form_rows, start=1):
        afm = norm_afm(str(row.get("employee_afm") or ""))
        if not afm:
            continue
        import_action, intervals, schedule_type, errors = _parse_form_row(row)
        import_rows.append(
            _build_import_row(
                row_no=idx,
                sheet_name="html_form",
                work_date=work_date,
                afm=afm,
                eponymo=str(row.get("eponymo") or "").strip() or None,
                onoma=str(row.get("onoma") or "").strip() or None,
                import_action=import_action,
                intervals=intervals,
                schedule_type=schedule_type,
                current_schedule=current_schedule,
                row_errors=errors,
            )
        )

    for row in import_rows:
        row["current_label"] = format_snapshot_label(row.get("current_snapshot") or [])
        row["proposed_label"] = format_snapshot_label(row.get("proposed_snapshot") or [])

    summary = summarize_import_rows(import_rows)
    return {
        "work_date": work_date,
        "date_iso": date_iso[:10],
        "rows": import_rows,
        "summary": summary,
    }


def submit_day_form(
    ctx: dict[str, Any],
    *,
    date_iso: str,
    form_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    preview = preview_day_form(ctx, date_iso=date_iso, form_rows=form_rows)
    to_apply = [
        row for row in preview.get("rows") or []
        if row.get("change_kind") in ("new", "update")
        and not row.get("validation_errors")
    ]
    if not to_apply:
        return {
            "success": True,
            "applied": 0,
            "failed": 0,
            "skipped": len(preview.get("rows") or []),
            "results": [],
            "summary": preview.get("summary") or {},
            "message": "Δεν υπάρχουν αλλαγές προς αποστολή.",
        }

    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return {"success": False, "error": "Αποτυχία σύνδεσης Ergani API (web user)"}

    applied = 0
    failed = 0
    results: list[dict[str, Any]] = []
    batch_meta = {
        "batch_id": None,
        "original_filename": "html_day_form",
        "week_label": f"Ημέρα {preview.get('work_date')}",
        "source": "html_day_form",
    }

    for row in to_apply:
        row_payload = dict(row)
        row_payload["comments"] = "Εισαγωγή ημερήσιου ωραρίου από φόρμα HTML"
        try:
            result = apply_import_row(ctx, row_payload, bearer, batch_meta=batch_meta)
        except Exception as ex:
            current_app.logger.exception("schedule day form apply failed")
            result = {"success": False, "error": str(ex), "http_status": 500}

        ok = bool(result.get("success"))
        if ok:
            applied += 1
        else:
            failed += 1
        results.append({
            "employee_afm": row.get("employee_afm"),
            "eponymo": row.get("eponymo"),
            "work_date": row.get("work_date"),
            "success": ok,
            "protocol": result.get("protocol"),
            "error": result.get("error"),
        })

    schedule_sync = None
    if applied > 0:
        try:
            sync_result = fetch_and_save_schedule_for_ctx(
                ctx,
                from_iso=date_iso[:10],
                to_iso=date_iso[:10],
                max_days=1,
            )
            schedule_sync = {
                "attempted": True,
                "success": bool(sync_result.get("success")),
                "from": date_iso[:10],
                "to": date_iso[:10],
                "count": int(sync_result.get("count") or 0),
                "detail": str(sync_result.get("detail") or "").strip() or None,
            }
        except Exception as ex:
            current_app.logger.exception("schedule day form post-sync failed")
            schedule_sync = {
                "attempted": True,
                "success": False,
                "from": date_iso[:10],
                "to": date_iso[:10],
                "count": 0,
                "detail": str(ex),
            }

    summary = dict(preview.get("summary") or {})
    summary["applied_ok"] = applied
    summary["applied_failed"] = failed

    return {
        "success": failed == 0,
        "applied": applied,
        "failed": failed,
        "results": results,
        "summary": summary,
        "schedule_sync": schedule_sync,
        "work_date": preview.get("work_date"),
    }
