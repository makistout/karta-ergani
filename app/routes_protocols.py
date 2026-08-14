"""API καταλόγου πρωτοκόλλων Ergani (WorkCardSearch)."""

from __future__ import annotations

import pyodbc
from flask import Blueprint, jsonify, request

from app.access_control import is_admin_role
from app.http_helpers import resolve_active_store
from app.portal_card_protocol_sync import iter_card_protocol_sync_events
from app.protocol_deduction_match import apply_protocol_sync
from app.repo_ergani_protocol import list_protocols_for_store_range, table_missing_message
from app.sync_jobs import get_sync_job
from app.sync_route_util import (
    parse_sync_request,
    should_run_async,
    start_async_portal_sync,
)

protocols_bp = Blueprint("protocols", __name__, url_prefix="/api/protocols")


def _db_error(exc: Exception):
    msg = table_missing_message(exc)
    if msg:
        return jsonify({
            "error": msg,
            "protocols": [],
            "db_setup": "sql/alter_add_karta_ergani_protocol.sql",
        }), 503
    raise exc


def _dates_from_request() -> tuple[str | None, str | None]:
    from_iso = request.args.get("from") or request.args.get("date")
    to_iso = request.args.get("to") or from_iso
    if not from_iso:
        return None, None
    return str(from_iso).strip()[:10], str(to_iso or from_iso).strip()[:10]


@protocols_bp.get("/list")
def protocols_list():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "protocols": []}), 400
    from_iso, to_iso = _dates_from_request()
    if not from_iso:
        return jsonify({"error": "Λείπει date ή from/to"}), 400
    try:
        rows = list_protocols_for_store_range(int(ctx["id"]), from_iso, to_iso)
    except pyodbc.Error as ex:
        return _db_error(ex)
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx["branch_aa"],
        },
        "from": from_iso,
        "to": to_iso,
        "count": len(rows),
        "protocols": rows,
    })


@protocols_bp.post("/sync")
def protocols_sync_route():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    if not is_admin_role():
        return jsonify({"error": "Απαιτείται ρόλος διαχειριστή"}), 403
    data = request.get_json(silent=True) or {}
    from_iso, to_iso, dates = parse_sync_request(data)
    if not from_iso:
        return jsonify({"error": "Λείπει date ή from/to"}), 400

    if should_run_async(data, dates):
        store_ctx = dict(ctx)

        def _runner(job_id: str):
            last_sync: dict | None = None
            for ev in iter_card_protocol_sync_events(
                store_ctx,
                from_iso=from_iso,
                to_iso=to_iso,
                max_days=31,
                run_id=job_id,
            ):
                yield ev
                if ev.get("event") == "done":
                    last_sync = ev.get("sync") or {}
            if last_sync and last_sync.get("success"):
                match = apply_protocol_sync(
                    int(store_ctx["id"]),
                    str(store_ctx.get("employer_afm") or ""),
                    str(store_ctx.get("branch_aa") or "0"),
                    from_iso=from_iso,
                    to_iso=to_iso,
                )
                yield {
                    "event": "progress",
                    "message": match.get("detail") or "1-1 απαγωγή",
                }

        return start_async_portal_sync(
            _runner,
            label="protocol_sync",
            store_id=int(ctx["id"]),
        )

    try:
        result = None
        for ev in iter_card_protocol_sync_events(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=31,
        ):
            if ev.get("event") == "done":
                result = ev.get("sync") or {}
            elif ev.get("event") == "error":
                return jsonify({
                    "success": False,
                    "error": ev.get("message") or "Αποτυχία sync πρωτοκόλλων",
                }), 502
        if not result:
            return jsonify({"success": False, "error": "Διακόπηκε ο συγχρονισμός"}), 502
        match = {}
        if result.get("success"):
            match = apply_protocol_sync(
                int(ctx["id"]),
                str(ctx.get("employer_afm") or ""),
                str(ctx.get("branch_aa") or "0"),
                from_iso=from_iso,
                to_iso=to_iso,
            )
        return jsonify({
            "success": bool(result.get("success")),
            "sync": result,
            "protocol_match": match,
            "error": result.get("detail") if not result.get("success") else None,
        })
    except pyodbc.Error as ex:
        return _db_error(ex)


@protocols_bp.get("/sync/status/<job_id>")
def protocols_sync_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο job"}), 404
    return jsonify(job)
