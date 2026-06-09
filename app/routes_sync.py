"""Συγχρονισμός Ergani — ξεχωριστό blueprint."""

from __future__ import annotations

from flask import Blueprint, after_this_request, jsonify

from app.http_helpers import ensure_ergani_bearer, resolve_active_store
from app.sync_jobs import create_portal_sync_job, get_sync_job, run_portal_sync_job
from app.sync_service import iter_store_sync_events

sync_bp = Blueprint("sync", __name__, url_prefix="/api/ergani")


@sync_bp.post("/sync-all")
def sync_all():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({
            "error": "Αποτυχία σύνδεσης Ergani — επιλέξτε ξανά το κατάστημα",
        }), 401

    job_id = create_portal_sync_job(
        label="ergani_sync_all",
        store_id=int(ctx["id"]),
    )

    @after_this_request
    def _start_sync(response):
        run_portal_sync_job(
            job_id,
            lambda: iter_store_sync_events(
                bearer,
                str(ctx["employer_afm"]),
                str(ctx.get("branch_aa") or "0"),
                int(ctx["id"]),
                api_base_url=ctx.get("api_base_url"),
                run_id=job_id,
                store_name=ctx.get("name"),
            ),
        )
        return response

    return jsonify({"async": True, "job_id": job_id})


@sync_bp.get("/sync-all/status/<job_id>")
def sync_all_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο ή ολοκληρωμένο job"}), 404
    return jsonify(job)
