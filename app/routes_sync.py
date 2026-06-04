"""Συγχρονισμός Ergani — ξεχωριστό blueprint."""

from __future__ import annotations

from flask import Blueprint, jsonify

from app.http_helpers import ensure_ergani_bearer, resolve_active_store
from app.sync_service import sync_store_from_ergani

sync_bp = Blueprint("sync", __name__, url_prefix="/api/ergani")


@sync_bp.post("/sync-all")
def sync_all():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    bearer = ensure_ergani_bearer(ctx)
    if not bearer:
        return jsonify({"error": "Αποτυχία σύνδεσης Ergani — επιλέξτε ξανά το κατάστημα"}), 401
    result = sync_store_from_ergani(
        bearer,
        str(ctx["employer_afm"]),
        str(ctx.get("branch_aa") or "0"),
        int(ctx["id"]),
        api_base_url=ctx.get("api_base_url"),
    )
    return jsonify(result)
