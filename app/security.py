"""Προαιρετική προστασία API (token) — όχι αντικατάσταση πλήρους login UI."""

from __future__ import annotations

import secrets

from flask import Flask, jsonify, request

from config import Config

_PUBLIC_API_PATHS = frozenset({"/health", "/api/local/health"})


def register_api_token_guard(app: Flask) -> None:
    token = (Config.OFFICE_API_TOKEN or "").strip()
    if not token:
        return

    @app.before_request
    def _require_office_token():
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
