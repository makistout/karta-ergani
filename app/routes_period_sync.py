"""API συγχρονισμού περιόδου (από–έως)."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.http_helpers import ensure_ergani_bearer, resolve_active_store
from app.period_sync import iter_period_sync_events
from app.sync_jobs import get_sync_job
from app.sync_route_util import parse_sync_request, start_async_portal_sync

period_sync_bp = Blueprint("period_sync", __name__, url_prefix="/api/period-sync")


@period_sync_bp.post("/run")
def period_sync_run():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({
            "error": "Αποτυχία σύνδεσης Ergani — επιλέξτε ξανά το κατάστημα",
        }), 401

    data = request.get_json(silent=True) or {}
    from_iso, to_iso, dates = parse_sync_request(data)
    if not from_iso:
        return jsonify({"error": "Λείπει from ή date"}), 400
    if not dates:
        return jsonify({"error": "Μη έγκυρο διάστημα ημερομηνιών"}), 400

    store_ctx = dict(ctx)
    return start_async_portal_sync(
        lambda job_id: iter_period_sync_events(
            store_ctx,
            bearer,
            from_iso,
            to_iso,
            run_id=job_id,
        ),
        label="period_sync",
        store_id=int(ctx["id"]),
    )


@period_sync_bp.get("/run/status/<job_id>")
def period_sync_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο ή ολοκληρωμένο job"}), 404
    return jsonify(job)
