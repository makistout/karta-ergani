"""Προστασία εφαρμογής — session login + προαιρετικό API token."""

from __future__ import annotations

import secrets

from flask import Flask, jsonify, request

from config import Config

_PUBLIC_API_PATHS = frozenset({"/health", "/api/local/health", "/api/telegram/webhook"})


def register_api_token_guard(app: Flask) -> None:
    """Εναλλακτική πρόσβαση API με X-Office-Token (integrations). Το login guard το χειρίζεται."""
    token = (Config.OFFICE_API_TOKEN or "").strip()
    if not token:
        return

    @app.before_request
    def _require_office_token():
        from app.office_auth import is_office_authenticated, office_login_enabled

        if office_login_enabled() and is_office_authenticated():
            return None
        path = request.path or ""
        if path in _PUBLIC_API_PATHS:
            return None
        if not path.startswith("/api/"):
            return None
        got = (request.headers.get("X-Office-Token") or "").strip()
        if not got:
            auth = (request.headers.get("Authorization") or "").strip()
            if auth.lower().startswith("bearer "):
                got = auth[7:].strip()
        if got and secrets.compare_digest(got, token):
            return None
        return jsonify({"error": "Απαιτείται έγκυρο X-Office-Token"}), 401


def register_security(app: Flask) -> None:
    from app.office_auth import register_login_guard

    register_login_guard(app)
    register_api_token_guard(app)
