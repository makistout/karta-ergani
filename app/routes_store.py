"""API καταστημάτων — ξεχωριστό blueprint."""

from __future__ import annotations

from typing import Any

import requests
from flask import Blueprint, after_this_request, jsonify, request, session

from app import repo_store as repo
from app.ergani_env import env_label, normalize_ergani_env, store_api_context
from app.ergani_env import client_for_store
from app.http_helpers import json_or_text
from app.portal_auth import verify_store_wizard
from app.ergani_env import api_login_credentials
from app.ergani_client import ErganiClient
from app.store_credentials_util import MASKED, merge_secret, mask_store_secrets
from app.sync_jobs import create_portal_sync_job, get_sync_job, run_portal_sync_job
from app.sync_service import iter_store_sync_events

store_bp = Blueprint("store", __name__, url_prefix="/api/store")


def _json_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        row = {}
        for k, v in r.items():
            row[k] = v.isoformat() if hasattr(v, "isoformat") else v
        out.append(row)
    return out


def _parse_credential_body(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    store_id = data.get("id")
    existing = repo.get_store_config(int(store_id)) if store_id else None
    password = merge_secret(data.get("password"), existing, "password")
    web_password = merge_secret(data.get("web_password"), existing, "web_password")
    web_username = (data.get("web_username") or "").strip() or None
    if not web_username and existing:
        web_username = existing.get("web_username")
    return {
        "name": (data.get("name") or "").strip(),
        "username": (data.get("username") or "").strip(),
        "password": password,
        "usertype": (data.get("usertype") or "01").strip(),
        "web_username": web_username,
        "web_password": web_password or None,
        "employer_afm": (data.get("employer_afm") or "").strip()
        or (existing or {}).get("employer_afm")
        or (data.get("username") or "").strip(),
        "branch_aa": (data.get("branch_aa") or (existing or {}).get("branch_aa") or "0").strip(),
        "ergani_env": normalize_ergani_env(data.get("ergani_env")),
        "store_id": int(store_id) if store_id else None,
    }, existing


@store_bp.get("/list")
def list_stores():
    rows = repo.list_store_configs()
    return jsonify(_json_rows([mask_store_secrets(r) for r in rows]))


@store_bp.get("/<int:store_id>")
def get_store(store_id: int):
    """Στοιχεία καταστήματος για φόρμα επεξεργασίας — πλήρη passwords (απαιτείται login)."""
    cfg = repo.get_store_config(store_id)
    if not cfg:
        return jsonify({"error": "Δεν βρέθηκε κατάστημα"}), 404
    return jsonify(_json_rows([cfg])[0])


def _resolve_wizard_secrets(data: dict, existing: dict | None) -> dict[str, str]:
    store_id = data.get("id")
    ex = existing or (repo.get_store_config(int(store_id)) if store_id else None)

    def pick(*keys: str, db_key: str | None = None) -> str:
        s = ""
        for key in keys:
            raw = data.get(key)
            if raw is None:
                continue
            cand = str(raw).strip() if isinstance(raw, str) else str(raw or "")
            if cand:
                s = cand
                break
        if s == MASKED and ex:
            return str(ex.get(db_key or keys[0]) or "")
        return s

    return {
        "web_username": pick("web_username", db_key="web_username"),
        "web_password": pick("web_password", db_key="web_password"),
        "admin_username": pick("username", "admin_username", db_key="username"),
        "admin_password": pick("password", "admin_password", db_key="password"),
        "admin_usertype": (data.get("usertype") or (ex or {}).get("usertype") or "01").strip(),
    }


@store_bp.post("/verify-portal")
@store_bp.post("/verify-wizard")
def verify_wizard_credentials():
    """Βήμα 1: web → Ergani API, admin → portal parse."""
    data = request.get_json(silent=True) or {}
    store_id = data.get("id")
    existing = repo.get_store_config(int(store_id)) if store_id else None
    sec = _resolve_wizard_secrets(data, existing)
    env = normalize_ergani_env(data.get("ergani_env"))
    try:
        result = verify_store_wizard(
            web_username=sec["web_username"],
            web_password=sec["web_password"],
            admin_username=sec["admin_username"],
            admin_password=sec["admin_password"],
            admin_usertype=sec["admin_usertype"],
            ergani_env=env,
        )
    except ValueError as ex:
        return jsonify({"success": False, "error": str(ex)}), 400
    except RuntimeError as ex:
        return jsonify({"success": False, "error": str(ex)}), 401
    except requests.RequestException as ex:
        return jsonify({"success": False, "error": f"Σφάλμα δικτύου: {ex}"}), 502
    return jsonify(result)


@store_bp.post("/credentials")
def save_store_credentials():
    """Βήμα 1 wizard: admin + web διαπιστευτήρια."""
    data = request.get_json(silent=True) or {}
    fields, existing = _parse_credential_body(data)
    if not fields["name"]:
        return jsonify({"error": "Υποχρευτικό όνομα καταστήματος"}), 400
    if not fields["web_username"] or not fields["web_password"]:
        return jsonify({"error": "Υποχρευτικά web_username και web_password (API)"}), 400
    if not fields["username"] or not fields["password"]:
        return jsonify({"error": "Υποχρευτικά admin username και password (portal)"}), 400
    try:
        saved_id = repo.save_store_credentials(
            name=fields["name"],
            username=fields["username"],
            password=fields["password"],
            usertype=fields["usertype"],
            ergani_env=fields["ergani_env"],
            employer_afm=fields["employer_afm"],
            branch_aa=fields["branch_aa"],
            web_username=fields["web_username"],
            web_password=fields["web_password"],
            store_id=fields["store_id"],
        )
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 404
    return jsonify({"success": True, "id": saved_id})


@store_bp.post("/save")
def save_store():
    data = request.get_json(silent=True) or {}
    fields, existing = _parse_credential_body(data)
    if not fields["name"]:
        return jsonify({"error": "Υποχρευτικό όνομα καταστήματος"}), 400
    if not fields["web_username"] or not fields["web_password"]:
        return jsonify({"error": "Υποχρευτικά web_username και web_password (API)"}), 400
    if not fields["username"] or not fields["password"]:
        return jsonify({"error": "Υποχρευτικά admin username και password (portal)"}), 400
    if not fields["employer_afm"]:
        return jsonify({"error": "Υποχρεωτικό employer_afm"}), 400
    saved = repo.save_store_config(
        name=fields["name"],
        username=fields["username"],
        password=fields["password"],
        usertype=fields["usertype"],
        ergani_env=fields["ergani_env"],
        employer_afm=fields["employer_afm"],
        branch_aa=fields["branch_aa"],
        web_username=fields["web_username"],
        web_password=fields["web_password"],
        sepe_code=data.get("sepe_code"),
        sepe_desc=data.get("sepe_desc"),
        oaed_code=data.get("oaed_code"),
        oaed_desc=data.get("oaed_desc"),
        kad_code=data.get("kad_code"),
        kad_desc=data.get("kad_desc"),
        kallikratis_code=data.get("kallikratis_code"),
        kallikratis_desc=data.get("kallikratis_desc"),
        store_id=fields["store_id"],
    )
    return jsonify({"success": True, "id": saved})


@store_bp.post("/record-sync")
def record_store_sync():
    """Καταγραφή επιτυχούς συγχρονισμού — καλείται από το UI μετά το portal sync."""
    from app.http_helpers import resolve_active_store

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Δεν έχει επιλεγεί κατάστημα"}), 400
    data = request.get_json(silent=True) or {}
    kind = (data.get("kind") or "").strip().lower()
    sid = int(ctx["id"])
    if kind == "work_log":
        repo.touch_work_log_sync(sid)
    elif kind == "schedule":
        repo.touch_schedule_sync(sid)
    else:
        return jsonify({"error": "Άγνωστος τύπος sync (work_log | schedule)"}), 400
    cfg = repo.get_store_config(sid) or {}

    def _iso_dt(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    sched_at = repo.effective_schedule_sync_at(cfg)
    wl_at = repo.effective_work_log_sync_at(cfg)
    return jsonify({
        "success": True,
        "kind": kind,
        "schedule_last_sync_at": _iso_dt(sched_at),
        "work_log_last_sync_at": _iso_dt(wl_at),
    })


@store_bp.delete("/<int:store_id>")
def delete_store(store_id: int):
    repo.delete_store_config(store_id)
    if session.get("active_store_id") == store_id:
        session.pop("active_store_id", None)
        session.pop("ergani_bearer", None)
        session.pop("employer_afm", None)
        session.pop("branch_aa", None)
        session.pop("ergani_env", None)
    return jsonify({"success": True})


@store_bp.get("/active")
def active_store():
    from app.http_helpers import active_store_payload, resolve_active_store

    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"store": None})
    return jsonify({"store": active_store_payload(ctx)})


@store_bp.post("/select")
def select_store():
    data = request.get_json(silent=True) or {}
    store_id = data.get("id")
    if not store_id:
        return jsonify({"error": "Λείπει id"}), 400
    cfg = repo.get_store_config(int(store_id))
    if not cfg:
        return jsonify({"error": "Δεν βρέθηκε κατάστημα"}), 404
    ctx = store_api_context(cfg)
    client = client_for_store(cfg)
    api_user, api_pwd, api_ut = api_login_credentials(ctx)
    resp = client.authenticate(api_user, api_pwd, api_ut)
    payload = json_or_text(resp)
    if not resp.ok or not isinstance(payload, dict) or not payload.get("accessToken"):
        return jsonify({
            "error": "Αποτυχία σύνδεσης Ergani",
            "ergani_env": ctx["ergani_env"],
            "ergani_env_label": env_label(ctx["ergani_env"]),
            "api_base": ctx["api_base_url"],
            "upstream_status": resp.status_code,
            "upstream_data": payload,
        }), 401
    token = str(payload["accessToken"])
    session["active_store_id"] = cfg["id"]
    session["ergani_bearer"] = token
    session["employer_afm"] = ctx["employer_afm"]
    session["branch_aa"] = ctx["branch_aa"]
    session["ergani_env"] = ctx["ergani_env"]

    job_id = create_portal_sync_job(
        label="store_select",
        store_id=int(cfg["id"]),
    )
    store_payload = {
        "id": ctx["id"],
        "name": ctx["name"],
        "employer_afm": ctx["employer_afm"],
        "branch_aa": ctx["branch_aa"],
        "ergani_env": ctx["ergani_env"],
        "ergani_env_label": ctx["ergani_env_label"],
        "api_base_url": ctx.get("api_base_url"),
        "portal_base_url": ctx.get("portal_base_url"),
    }

    @after_this_request
    def _start_store_sync(response):
        run_portal_sync_job(
            job_id,
            lambda: iter_store_sync_events(
                token,
                ctx["employer_afm"],
                ctx["branch_aa"],
                int(cfg["id"]),
                api_base_url=ctx["api_base_url"],
                run_id=job_id,
                store_name=ctx.get("name"),
            ),
        )
        return response

    return jsonify({
        "success": True,
        "store": store_payload,
        "async": True,
        "job_id": job_id,
    })


@store_bp.get("/select/status/<job_id>")
def select_store_status(job_id: str):
    job = get_sync_job(job_id)
    if not job:
        return jsonify({"error": "Άγνωστο ή ολοκληρωμένο job"}), 404
    return jsonify(job)


@store_bp.get("/<int:store_id>/notify-recipients")
def get_notify_recipients(store_id: int):
    cfg = repo.get_store_config(store_id)
    if not cfg:
        return jsonify({"error": "Δεν βρέθηκε κατάστημα", "recipients": []}), 404
    from app.repo_notify_recipients import (
        list_notify_recipients,
        notify_recipients_table_missing_message,
    )

    try:
        rows = list_notify_recipients(store_id)
    except Exception as ex:
        hint = notify_recipients_table_missing_message(ex)
        if hint:
            return jsonify({"error": hint, "recipients": [], "db_setup": hint}), 500
        raise
    return jsonify({
        "store_id": store_id,
        "recipients": _json_rows(rows),
    })


@store_bp.put("/<int:store_id>/notify-recipients")
def put_notify_recipients(store_id: int):
    cfg = repo.get_store_config(store_id)
    if not cfg:
        return jsonify({"error": "Δεν βρέθηκε κατάστημα"}), 404
    from app.repo_notify_recipients import (
        list_notify_recipients,
        notify_recipients_table_missing_message,
        replace_notify_recipients,
    )

    data = request.get_json(silent=True) or {}
    rows = data.get("recipients")
    if not isinstance(rows, list):
        return jsonify({"error": "Αναμενόταν recipients[]"}), 400
    try:
        n = replace_notify_recipients(store_id, rows)
        saved = list_notify_recipients(store_id)
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 400
    except Exception as ex:
        hint = notify_recipients_table_missing_message(ex)
        if hint:
            return jsonify({"error": hint, "db_setup": hint}), 500
        return jsonify({"error": f"Αποτυχία αποθήκευσης ληπτών: {ex}"}), 500
    return jsonify({"success": True, "count": n, "recipients": _json_rows(saved)})
