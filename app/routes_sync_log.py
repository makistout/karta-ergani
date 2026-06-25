"""API προβολής sync logs από τη βάση."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.http_helpers import resolve_active_store
from app import repo_sync_log

sync_log_bp = Blueprint("sync_log", __name__, url_prefix="/api/sync-log")

_OPERATION_LABELS = {
    "store_select": "Επιλογή καταστήματος",
    "ergani_sync_all": "Συγχρονισμός Ergani",
    "schedule_sync": "Ψηφιακό ωράριο",
    "period_sync": "Συγχρονισμός περιόδου",
    "work_log_sync": "Πραγματική απασχόληση",
    "scheduled_today_sync": "Αυτόματος συγχρονισμός",
    "scheduled_post_sync_notify": "Ειδοποιήσεις μετά το sync",
}


def _label_operation(op: str | None) -> str:
    if not op:
        return "—"
    return _OPERATION_LABELS.get(op, op)


@sync_log_bp.get("/runs")
def sync_log_runs():
    if not repo_sync_log.tables_available():
        return jsonify({
            "error": "Δεν υπάρχουν οι πίνακες log στη βάση.",
            "db_setup": "sql/alter_add_karta_sync_log.sql",
        }), 503

    store_id = request.args.get("store_id", type=int)
    active_only = request.args.get("active_store") in ("1", "true", "yes")
    if active_only:
        ctx = resolve_active_store()
        if ctx:
            store_id = int(ctx["id"])

    limit = request.args.get("limit", default=50, type=int) or 50
    offset = request.args.get("offset", default=0, type=int) or 0
    q = (request.args.get("q") or "").strip() or None
    repo_sync_log.reconcile_stale_runs()
    runs = repo_sync_log.list_runs(store_id=store_id, q=q, limit=limit, offset=offset)
    total = repo_sync_log.count_runs(store_id=store_id, q=q)
    for r in runs:
        r["operation_label"] = _label_operation(r.get("operation"))
    return jsonify({
        "runs": runs,
        "count": total,
        "store_id": store_id,
        "operation_labels": _OPERATION_LABELS,
    })


@sync_log_bp.get("/runs/<run_id>")
def sync_log_run_detail(run_id: str):
    if not repo_sync_log.tables_available():
        return jsonify({
            "error": "Δεν υπάρχουν οι πίνακες log στη βάση.",
            "db_setup": "sql/alter_add_karta_sync_log.sql",
        }), 503
    repo_sync_log.reconcile_stale_runs()
    run = repo_sync_log.get_run(run_id)
    if not run:
        return jsonify({"error": "Δεν βρέθηκε εγγραφή"}), 404
    run["operation_label"] = _label_operation(run.get("operation"))
    return jsonify(run)


@sync_log_bp.get("/notifications")
def sync_log_notifications():
    if not repo_sync_log.tables_available():
        return jsonify({
            "error": "Δεν υπάρχουν οι πίνακες log στη βάση.",
            "db_setup": "sql/alter_add_karta_sync_log.sql",
        }), 503

    store_id = request.args.get("store_id", type=int)
    q = (request.args.get("q") or "").strip() or None
    limit = request.args.get("limit", default=200, type=int) or 200
    offset = request.args.get("offset", default=0, type=int) or 0
    rows = repo_sync_log.list_notification_sends(
        store_id=store_id,
        q=q,
        limit=limit,
        offset=offset,
    )
    total = repo_sync_log.count_notification_sends(store_id=store_id, q=q)
    return jsonify({
        "notifications": rows,
        "count": total,
        "store_id": store_id,
        "q": q,
    })
