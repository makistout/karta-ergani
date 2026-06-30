"""API προβολής ανεξάρτητου audit trail."""

from __future__ import annotations

import json
import re
from typing import Any

from flask import Blueprint, jsonify, request

from app.audit_log import list_audit_events

audit_bp = Blueprint("audit", __name__, url_prefix="/api/audit")


def _redact_request_path(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    parts = value.split("/")
    for marker in ("today-hit", "hit", "punch"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts):
                parts[idx + 1] = "***"
    return "/".join(parts)


def _token_from_request_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"/today-hit/([^/]+)", value)
    if match:
        return match.group(1)
    return None


def _token_from_details(details: dict[str, Any] | None) -> str | None:
    if not isinstance(details, dict):
        return None
    request_data = details.get("request")
    if isinstance(request_data, dict):
        token = str(request_data.get("token") or "").strip()
        if token and token != "***":
            return token
    query = details.get("query")
    if isinstance(query, dict):
        raw = query.get("t")
        if isinstance(raw, list) and raw:
            token = str(raw[0] or "").strip()
            if token and token != "***":
                return token
        elif raw:
            token = str(raw).strip()
            if token and token != "***":
                return token
    return None


def _notification_actor(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        from app.repo_today_alert import get_today_alert_token_row

        row = get_today_alert_token_row(token)
    except Exception:
        return None
    if not row:
        return None
    name = str(row.get("recipient_name") or "").strip()
    mobile = str(row.get("mobile") or "").strip()
    return {
        "recipient_id": row.get("recipient_id"),
        "name": name or mobile or "—",
        "mobile": mobile,
        "store_id": row.get("store_id"),
        "store_name": row.get("store_name"),
    }


def _json_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        row = {}
        details: dict[str, Any] | None = None
        for k, v in r.items():
            if k == "request_path":
                row[k] = _redact_request_path(v)
                continue
            if k == "details_json" and isinstance(v, str):
                try:
                    details = json.loads(v)
                    row["details"] = details
                except json.JSONDecodeError:
                    row[k] = v
                continue
            row[k] = v.isoformat() if hasattr(v, "isoformat") else v
        actor = None
        if isinstance(details, dict):
            maybe = details.get("notification_actor")
            if isinstance(maybe, dict):
                actor = maybe
        if actor is None:
            actor = _notification_actor(
                _token_from_details(details) or _token_from_request_path(r.get("request_path"))
            )
        if actor:
            row["notification_actor"] = actor
        out.append(row)
    return out


@audit_bp.get("/list")
def audit_list():
    raw_store = request.args.get("store_id")
    store_id = int(raw_store) if raw_store and raw_store.isdigit() else None
    kind = str(request.args.get("kind") or "").strip() or None
    if kind not in (None, "today_notifications", "work_card_punches", "auth"):
        kind = None
    try:
        limit = int(request.args.get("limit", "200"))
    except ValueError:
        limit = 200
    rows = list_audit_events(store_id=store_id, kind=kind, limit=limit)
    return jsonify({
        "count": len(rows),
        "audit": _json_rows(rows),
    })
