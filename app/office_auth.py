"""Σύνδεση γραφείου (session) — username/password από περιβάλλον."""

from __future__ import annotations

import secrets
from urllib.parse import quote

from flask import Flask, jsonify, redirect, request, session

from config import Config

SESSION_LOGGED_IN = "office_logged_in"
SESSION_USER = "office_user"

_PUBLIC_EXACT = frozenset({
    "/health",
    "/api/local/health",
    "/api/telegram/webhook",
    "/ui/login",
    "/api/auth/login",
    "/api/auth/status",
    "/api/auth/logout",
    "/favicon.ico",
})

_PUBLIC_PREFIXES = ("/static/",)


def office_login_enabled() -> bool:
    user, pwd = Config.office_login_credentials()
    return bool(user and pwd)


def office_login_credentials() -> tuple[str, str]:
    return Config.office_login_credentials()


def is_office_authenticated() -> bool:
    return bool(session.get(SESSION_LOGGED_IN))


def login_office_user(username: str, password: str) -> bool:
    expected_user, expected_pwd = office_login_credentials()
    if not expected_user or not expected_pwd:
        return False
    user = (username or "").strip()
    pwd = password or ""
    if not secrets.compare_digest(user, expected_user):
        return False
    if not secrets.compare_digest(pwd, expected_pwd):
        return False
    session[SESSION_LOGGED_IN] = True
    session[SESSION_USER] = user
    session.permanent = True
    return True


def logout_office_user() -> None:
    session.pop(SESSION_LOGGED_IN, None)
    session.pop(SESSION_USER, None)


def _path_is_public(path: str, method: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    if path == "/api/work-card/event" and method == "POST":
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
        if is_office_authenticated() or _office_api_token_ok():
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
