"""API Ergani για wizard καταστήματος — ξεχωριστό blueprint."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.ergani_client import ErganiClient
from app.ergani_env import base_url_from_request, env_label, ergani_env_from_request
from app.ergani_parse import (
    extract_catalog_items,
    parse_branches,
    parse_employer_afm,
    unwrap_ergani_data,
)
from app.http_helpers import bearer_from_request, json_or_text
from app.repo_kallikratis import search_kallikratis

ergani_bp = Blueprint("ergani", __name__, url_prefix="/api/ergani")

_CATALOG_MAP = {
    "sepe": "Sepe",
    "tees": "Sepe",
    "oaed": "Oaed",
    "kad": "Stakod",
    "stakod": "Stakod",
}


@ergani_bp.post("/auth/authenticate")
def ergani_authenticate():
    body = request.get_json(silent=True) or {}
    username = (body.get("Username") or body.get("username") or "").strip()
    password = body.get("Password") or body.get("password") or ""
    usertype = (body.get("Usertype") or body.get("usertype") or "02").strip()
    if not username or not password:
        return jsonify({"error": "Υποχρεωτικά username και password"}), 400
    env = ergani_env_from_request(body)
    api_base = base_url_from_request(body)
    client = ErganiClient(api_base)
    resp = client.authenticate(username, password, usertype)
    parsed = json_or_text(resp)
    if not resp.ok or not isinstance(parsed, dict) or not parsed.get("accessToken"):
        detail = parsed if isinstance(parsed, str) else None
        return jsonify({
            "error": detail or "Αποτυχία αυθεντικοποίησης",
            "status": resp.status_code,
            "ergani_env": env,
            "ergani_env_label": env_label(env),
            "api_base": client.base_url,
            "data": parsed,
        }), resp.status_code if resp.status_code >= 400 else 401
    token = str(parsed["accessToken"])
    employer_afm = username[:9] if username.isdigit() and len(username) >= 9 else username
    ex01 = client.execute_service("EX_BASE_01", [], token)
    if ex01.ok:
        afm = parse_employer_afm(json_or_text(ex01))
        if afm:
            employer_afm = afm
    return jsonify({
        "success": True,
        "accessToken": token,
        "employer_afm": employer_afm,
        "accessTokenExpired": parsed.get("accessTokenExpired"),
        "ergani_env": env,
        "ergani_env_label": env_label(env),
        "api_base": api_base,
    })


def _require_bearer():
    bearer = bearer_from_request()
    if not bearer:
        return None, (jsonify({"error": "Απαιτείται Authorization: Bearer <token>"}), 401)
    return bearer, None


@ergani_bp.get("/branches")
def ergani_branches():
    bearer, err = _require_bearer()
    if err:
        return err
    client = ErganiClient(base_url_from_request())
    resp = client.execute_service("EX_BASE_02", [], bearer)
    parsed = json_or_text(resp)
    if not resp.ok:
        return jsonify({"error": "Αποτυχία EX_BASE_02", "status": resp.status_code, "data": parsed}), resp.status_code
    return jsonify({"branches": parse_branches(parsed)})


@ergani_bp.get("/catalog/<catalog_type>")
def ergani_catalog(catalog_type: str):
    bearer, err = _require_bearer()
    if err:
        return err
    key = catalog_type.strip().lower()
    param = _CATALOG_MAP.get(key)
    if not param:
        return jsonify({"error": "Τύπος: sepe, oaed, kad"}), 400
    client = ErganiClient(base_url_from_request())
    params = [{"ParameterName": "Parameter", "ParameterValue": param}]
    resp = client.execute_service("EX_BASE_03", params, bearer)
    parsed = json_or_text(resp)
    if not resp.ok:
        return jsonify({"error": "Αποτυχία EX_BASE_03", "status": resp.status_code, "data": parsed}), resp.status_code
    items = extract_catalog_items(unwrap_ergani_data(parsed))
    return jsonify({"catalog": key, "items": items})


@ergani_bp.get("/kallikratis/search")
def kallikratis_search():
    q = request.args.get("q", "").strip()
    try:
        lim = int(request.args.get("limit", "15"))
    except ValueError:
        lim = 15
    return jsonify({"query": q, "results": search_kallikratis(q, lim)})
