"""API αρχειοθέτησης ψηφιακής οργάνωσης (Τρέχουσα Κατάσταση)."""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.http_helpers import resolve_active_store
from app.portal_schedule_archive import iter_new_store_schedule_archive_events
from app.sync_jobs import get_sync_job
from app.sync_route_util import start_async_portal_sync

schedule_archive_bp = Blueprint(
    "schedule_archive", __name__, url_prefix="/api/schedule-archive"
)


@schedule_archive_bp.post("/new-store")
def schedule_archive_new_store():
    """Τελευταίο βήμα εισαγωγής καταστήματος: 1/1 έτους → 2 μήνες πριν."""
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400

    store_ctx = dict(ctx)
    return start_async_portal_sync(
        lambda job_id: iter_new_store_schedule_archive_events(
            store_ctx,
            run_id=job_id,
        ),
        label="new_store_schedule_archive",
        store_id=int(ctx["id"]),
    )


@schedule_archive_bp.get("/new-store/status/<job_id>")
def schedule_archive_new_store_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο ή ολοκληρωμένο job"}), 404
    return jsonify(job)
