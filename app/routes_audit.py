"""API προβολής ανεξάρτητου audit trail."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, jsonify, request

from app.audit_log import list_audit_events

audit_bp = Blueprint("audit", __name__, url_prefix="/api/audit")


def _json_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        row = {}
        for k, v in r.items():
            if k == "details_json" and isinstance(v, str):
                try:
                    row["details"] = json.loads(v)
                except json.JSONDecodeError:
                    row[k] = v
                continue
            row[k] = v.isoformat() if hasattr(v, "isoformat") else v
        out.append(row)
    return out


@audit_bp.get("/list")
def audit_list():
    raw_store = request.args.get("store_id")
    store_id = int(raw_store) if raw_store and raw_store.isdigit() else None
    try:
        limit = int(request.args.get("limit", "200"))
    except ValueError:
        limit = 200
    rows = list_audit_events(store_id=store_id, limit=limit)
    return jsonify({
        "count": len(rows),
        "audit": _json_rows(rows),
    })
