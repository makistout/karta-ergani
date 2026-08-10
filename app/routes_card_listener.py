"""Authenticated API used only by per-store WRKCardSE listener devices."""

from __future__ import annotations

import time

from flask import Blueprint, g, jsonify, request

from app import repo_card_listener as repo

card_listener_bp = Blueprint("card_listener", __name__, url_prefix="/api/card-listener/v1")


def _authenticate():
    device_id = (request.headers.get("X-Listener-Device") or "").strip()
    auth = (request.headers.get("Authorization") or "").strip()
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    device = repo.authenticate_device(
        device_id, token, version=(request.headers.get("X-Listener-Version") or "").strip(),
    )
    if not device:
        return None, (jsonify({"error": "invalid_listener_device"}), 401)
    g.card_listener_device = device
    return device, None


@card_listener_bp.get("/health")
def health():
    device, error = _authenticate()
    if error:
        return error
    from app.ergani_env import env_label, store_api_context
    from app.repo_store import get_store_config
    store = get_store_config(int(device["store_id"]))
    if not store:
        return jsonify({"error": "listener_store_not_found"}), 404
    ctx = store_api_context(store)
    return jsonify({
        "ok": True,
        "store_id": int(device["store_id"]),
        "ergani_env": ctx["ergani_env"],
        "ergani_env_label": env_label(ctx["ergani_env"]),
        "ergani_api_base_url": ctx["api_base_url"],
    })


@card_listener_bp.post("/network/refresh")
def refresh_network_identity():
    device, error = _authenticate()
    if error:
        return error
    from app.client_request import observed_peer_ip
    public_ip = observed_peer_ip(request)
    repo.update_device_public_ip(int(device["id"]), public_ip)
    return jsonify({"success": True, "public_ip": public_ip})


@card_listener_bp.get("/jobs/next")
def next_job():
    device, error = _authenticate()
    if error:
        return error
    wait_seconds = max(0, min(int(request.args.get("wait") or 25), 25))
    deadline = time.monotonic() + wait_seconds
    while True:
        job = repo.lease_next_job(int(device["store_id"]), str(device["device_id"]))
        if job:
            return jsonify({"job": job})
        if time.monotonic() >= deadline:
            return jsonify({"job": None})
        time.sleep(1)


@card_listener_bp.post("/jobs/<uuid:job_uuid>/result")
def job_result(job_uuid):
    device, error = _authenticate()
    if error:
        return error
    body = request.get_json(silent=True) or {}
    saved = repo.finish_job(
        int(device["store_id"]), str(device["device_id"]), str(job_uuid), body,
        submission_ip=device.get("last_seen_ip"),
    )
    if not saved:
        return jsonify({"error": "job_not_owned_or_not_active"}), 409
    return jsonify({"success": True})
