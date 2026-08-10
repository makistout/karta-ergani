"""Σύνδεση γραφείου (session) — username/password από περιβάλλον."""

from __future__ import annotations

import secrets
from urllib.parse import quote

from flask import Flask, jsonify, redirect, request, session

from app.access_control import (
    SESSION_PERMISSIONS,
    SESSION_ROLE,
    SESSION_SUPER_ADMIN,
    SESSION_USER_ID,
    has_permission,
    normalize_role,
    permission_for_path,
    permissions_for_role,
)
from app.landing_seo import seo_public_paths
from config import Config

SESSION_LOGGED_IN = "office_logged_in"
SESSION_USER = "office_user"
SESSION_MUST_CHANGE_PASSWORD = "office_must_change_password"
SESSION_TERMS_ACCEPTED = "office_terms_accepted"

_PUBLIC_EXACT = frozenset({
    "/",
    "/health",
    "/api/local/health",
    "/api/telegram/webhook",
    "/psifiaki-karta-ergasias",
    "/psifiaki-karta-ergasias/",
    "/ui/landing",
    "/ui/login",
    "/ui/verify-email",
    "/ui/forgot-password",
    "/ui/reset-password",
    "/ui/telegram-hit",
    "/ui/telegram-punch",
    "/ui/retro-hit",
    "/ui/retro-punch",
    "/ui/today-hit",
    "/ui/today-action",
    "/api/auth/login",
    "/api/auth/status",
    "/api/auth/logout",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/contact",
    "/api/users/verify-email",
    "/favicon.ico",
}) | seo_public_paths()

_PUBLIC_PREFIXES = ("/static/", "/api/card-listener/v1/")

# Σελίδες/API onboarding — επιτρέπονται όταν ο χρήστης είναι συνδεδεμένος
# αλλά δεν έχει ολοκληρώσει αλλαγή κωδικού / αποδοχή όρων.
_ONBOARDING_PATHS = frozenset({
    "/ui/change-password",
    "/ui/accept-terms",
    "/api/auth/change-password",
    "/api/auth/accept-terms",
    "/api/auth/terms",
    "/api/auth/status",
    "/api/auth/logout",
})


def office_login_enabled() -> bool:
    return bool(Config.office_users())


def office_login_credentials() -> tuple[str, str]:
    return Config.office_login_credentials()


def is_office_authenticated() -> bool:
    return bool(session.get(SESSION_LOGGED_IN))


def _set_onboarding_session(db_user: dict) -> None:
    session[SESSION_MUST_CHANGE_PASSWORD] = bool(db_user.get("must_change_password"))
    session[SESSION_TERMS_ACCEPTED] = bool(db_user.get("terms_accepted", True))


def clear_must_change_password_session() -> None:
    session[SESSION_MUST_CHANGE_PASSWORD] = False


def mark_terms_accepted_session() -> None:
    session[SESSION_TERMS_ACCEPTED] = True


def onboarding_redirect_path() -> str | None:
    """Επιστρέφει path υποχρεωτικού βήματος onboarding ή None."""
    if not is_office_authenticated():
        return None
    if bool(session.get(SESSION_MUST_CHANGE_PASSWORD)):
        return "/ui/change-password"
    if session.get(SESSION_TERMS_ACCEPTED) is False:
        return "/ui/accept-terms"
    return None


def login_office_user(username: str, password: str) -> bool:
    try:
        from app.repo_users import authenticate_user

        db_user = authenticate_user(username, password)
    except Exception:
        db_user = None
    if db_user:
        session[SESSION_LOGGED_IN] = True
        session[SESSION_USER] = db_user["username"]
        session[SESSION_USER_ID] = int(db_user["id"])
        session[SESSION_ROLE] = normalize_role(db_user.get("role"))
        session[SESSION_PERMISSIONS] = list(db_user.get("permissions") or [])
        session[SESSION_SUPER_ADMIN] = bool(db_user.get("is_super_admin"))
        _set_onboarding_session(db_user)
        session.permanent = True
        try:
            from app.scheduled_sync import enqueue_sync_allowed_stores_after_login

            enqueue_sync_allowed_stores_after_login(
                user_id=int(db_user["id"]),
                store_ids=None
                if bool(db_user.get("is_super_admin"))
                else list(db_user.get("store_ids") or []),
            )
        except Exception:
            pass
        return True

    users = Config.office_users()
    if not users:
        return False
    user = (username or "").strip()
    pwd = password or ""
    matched = None
    for candidate in users:
        expected_user = candidate.get("username") or ""
        expected_pwd = candidate.get("password") or ""
        if (
            secrets.compare_digest(user, expected_user)
            and secrets.compare_digest(pwd, expected_pwd)
        ):
            matched = candidate
            break
    if matched is None:
        return False
    session[SESSION_LOGGED_IN] = True
    session[SESSION_USER] = user
    role = normalize_role(matched.get("role"))
    session[SESSION_ROLE] = role
    session[SESSION_USER_ID] = None
    session[SESSION_PERMISSIONS] = sorted(permissions_for_role(role))
    session[SESSION_SUPER_ADMIN] = role == "super_admin"
    session[SESSION_MUST_CHANGE_PASSWORD] = False
    session[SESSION_TERMS_ACCEPTED] = True
    session.permanent = True
    return True


def logout_office_user() -> None:
    session.pop(SESSION_LOGGED_IN, None)
    session.pop(SESSION_USER, None)
    session.pop(SESSION_USER_ID, None)
    session.pop(SESSION_ROLE, None)
    session.pop(SESSION_PERMISSIONS, None)
    session.pop(SESSION_SUPER_ADMIN, None)
    session.pop(SESSION_MUST_CHANGE_PASSWORD, None)
    session.pop(SESSION_TERMS_ACCEPTED, None)


def _path_is_public(path: str, method: str) -> bool:
    norm = (path or "").strip()
    if len(norm) > 1 and norm.endswith("/"):
        norm = norm.rstrip("/")
    if norm in _PUBLIC_EXACT:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if norm.startswith(prefix):
            return True
    if norm == "/api/work-card/event" and method == "POST":
        return True
    if norm.startswith("/api/telegram/retro-hit/"):
        return True
    if norm.startswith("/api/telegram/today-hit/"):
        return True
    if norm.startswith("/api/telegram/today-action/"):
        return True
    if norm.startswith("/api/telegram/hit/"):
        return True
    if norm.startswith("/api/telegram/punch/"):
        return True
    return False


def _office_api_token_ok() -> bool:
    token = (Config.OFFICE_API_TOKEN or "").strip()
    if not token:
        return False
    got = (request.headers.get("X-Office-Token") or "").strip()
    if not got:
        auth = (request.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
    return bool(got) and secrets.compare_digest(got, token)


def register_login_guard(app: Flask) -> None:
    if not office_login_enabled():
        return

    @app.before_request
    def _require_office_login():
        path = request.path or ""
        if _path_is_public(path, request.method):
            return None
        token_ok = _office_api_token_ok()
        if is_office_authenticated() or token_ok:
            # Onboarding gate μόνο για session users (όχι office API token).
            if is_office_authenticated() and not token_ok:
                onboard_path = onboarding_redirect_path()
                if onboard_path and path not in _ONBOARDING_PATHS:
                    # Αλλαγή κωδικού προηγείται· μην αφήνουμε accept-terms πριν.
                    if bool(session.get(SESSION_MUST_CHANGE_PASSWORD)):
                        allowed = {
                            "/ui/change-password",
                            "/api/auth/change-password",
                            "/api/auth/status",
                            "/api/auth/logout",
                        }
                        if path not in allowed:
                            if path.startswith("/api/"):
                                return jsonify({
                                    "error": "Απαιτείται αλλαγή κωδικού",
                                    "redirect": "/ui/change-password",
                                    "must_change_password": True,
                                }), 403
                            return redirect("/ui/change-password")
                    elif path not in {
                        "/ui/accept-terms",
                        "/api/auth/accept-terms",
                        "/api/auth/terms",
                        "/api/auth/status",
                        "/api/auth/logout",
                    }:
                        if path.startswith("/api/"):
                            return jsonify({
                                "error": "Απαιτείται αποδοχή όρων χρήσης",
                                "redirect": "/ui/accept-terms",
                                "terms_accepted": False,
                            }), 403
                        return redirect("/ui/accept-terms")
            permission = permission_for_path(path, request.method)
            role = "admin" if token_ok else str(session.get(SESSION_ROLE) or "")
            if permission and not has_permission(permission, role=role):
                if path.startswith("/api/"):
                    return jsonify({
                        "error": "Δεν έχετε δικαίωμα πρόσβασης",
                        "permission": permission,
                    }), 403
                if path == "/" or path.startswith("/ui/"):
                    return redirect("/ui/")
                return jsonify({"error": "Δεν έχετε δικαίωμα πρόσβασης"}), 403
            return None
        if path.startswith("/api/"):
            return jsonify({
                "error": "Απαιτείται σύνδεση",
                "login": "/ui/login",
            }), 401
        if path == "/" or path.startswith("/ui/"):
            next_path = request.full_path.rstrip("?") if request.query_string else path
            if next_path.startswith("/ui/login"):
                return None
            return redirect(f"/ui/login?next={quote(next_path, safe='/:?&=')}")
        return redirect("/ui/login")
