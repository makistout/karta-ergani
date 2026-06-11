"""Αναφορές αρχικής σελίδας."""

from __future__ import annotations

from datetime import datetime

import pyodbc
from flask import Blueprint, jsonify, request

from app.card_report import build_card_status_report
from app.date_util import iso_to_ergani_dates
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


def _parse_date_iso(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    if "/" in s[:10]:
        try:
            return datetime.strptime(s[:10], "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            return None
    return s[:10] if len(s) >= 10 else None


@dashboard_bp.get("/card-report")
def card_report():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "rows": []}), 400

    from_iso = _parse_date_iso(request.args.get("from"))
    to_iso = _parse_date_iso(request.args.get("to"))
    single_iso = _parse_date_iso(request.args.get("date"))
    if single_iso:
        from_iso = to_iso = single_iso
    if not from_iso:
        from_iso = datetime.now(tz_athens()).date().isoformat()
    if not to_iso:
        to_iso = from_iso

    try:
        ergani_dates = iso_to_ergani_dates(from_iso, to_iso, 31)
        if len(ergani_dates) <= 1:
            report = build_card_status_report(
                ctx["employer_afm"],
                ctx["branch_aa"],
                date_iso=from_iso,
            )
        else:
            merged_rows: list[dict] = []
            merged_summary: dict[str, int] = {}
            merged_meta = {
                "schedule_count": 0,
                "work_log_count": 0,
                "card_event_count": 0,
                "has_schedule": False,
                "has_work_log": False,
            }
            for wd in ergani_dates:
                try:
                    day_iso = datetime.strptime(wd, "%d/%m/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    continue
                day = build_card_status_report(
                    ctx["employer_afm"],
                    ctx["branch_aa"],
                    date_iso=day_iso,
                )
                for row in day.get("rows") or []:
                    item = dict(row)
                    item["work_date"] = day.get("work_date") or wd
                    merged_rows.append(item)
                for key, val in (day.get("summary") or {}).items():
                    merged_summary[key] = merged_summary.get(key, 0) + int(val or 0)
                meta = day.get("meta") or {}
                merged_meta["schedule_count"] += int(meta.get("schedule_count") or 0)
                merged_meta["work_log_count"] += int(meta.get("work_log_count") or 0)
                merged_meta["card_event_count"] += int(
                    meta.get("card_event_count") or 0
                )
                merged_meta["has_schedule"] = merged_meta["has_schedule"] or bool(
                    meta.get("has_schedule")
                )
                merged_meta["has_work_log"] = merged_meta["has_work_log"] or bool(
                    meta.get("has_work_log")
                )
            report = {
                "date": from_iso,
                "date_to": to_iso,
                "work_date": f"{ergani_dates[0]} – {ergani_dates[-1]}",
                "work_dates": ergani_dates,
                "summary": merged_summary,
                "rows": merged_rows,
                "meta": merged_meta,
            }
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
