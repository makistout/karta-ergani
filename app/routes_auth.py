"""API σύνδεσης / αποσύνδεσης γραφείου."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from app.access_control import SESSION_ROLE, user_payload
from app.office_auth import (
    SESSION_USER,
    is_office_authenticated,
    login_office_user,
    logout_office_user,
    office_login_enabled,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.get("/status")
def auth_status():
    if not office_login_enabled():
        return jsonify({"login_required": False, "authenticated": True})
    return jsonify({
        "login_required": True,
        "authenticated": is_office_authenticated(),
        **(
            user_payload(session.get(SESSION_USER), session.get(SESSION_ROLE))
            if is_office_authenticated()
            else {"user": None, "role": None, "permissions": []}
        ),
    })


@auth_bp.post("/login")
def auth_login():
    if not office_login_enabled():
        return jsonify({"success": True, "login_required": False})
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return jsonify({"error": "Συμπληρώστε username και password"}), 400
    if not login_office_user(username, password):
        return jsonify({"error": "Λάθος username ή password"}), 401
    return jsonify({
        "success": True,
        **user_payload(session.get(SESSION_USER), session.get(SESSION_ROLE)),
    })


@auth_bp.post("/logout")
def auth_logout():
    logout_office_user()
    return jsonify({"success": True})
