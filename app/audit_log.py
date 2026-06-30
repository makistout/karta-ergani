"""Ανεξάρτητο audit trail για ενέργειες χρήστη/API."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pyodbc
from flask import Flask, g, has_request_context, request, session

from app.client_request import capture_client_context
from app.db import cursor
from app.office_auth import SESSION_USER

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REDACT_KEYS = (
    "password",
    "pass",
    "pwd",
    "token",
    "bearer",
    "authorization",
    "api_key",
    "pin",
    "notify_pin",
    "secret",
)


def _redact_key(key: str) -> bool:
    k = str(key or "").lower()
    return any(part in k for part in _REDACT_KEYS)


def _safe_payload(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "…"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            skey = str(key)[:128]
            out[skey] = "***" if _redact_key(skey) else _safe_payload(item, depth=depth + 1)
        if len(value) > 80:
            out["…"] = f"{len(value) - 80} more keys"
        return out
    if isinstance(value, list):
        out = [_safe_payload(item, depth=depth + 1) for item in value[:80]]
        if len(value) > 80:
            out.append(f"… {len(value) - 80} more items")
        return out
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str) and len(value) > 2000:
            return value[:2000] + "…"
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:2000]


def _json_dumps(value: Any, *, limit: int = 12000) -> str | None:
    if value is None:
        return None
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None
    return raw[:limit]


def _actor_from_request() -> tuple[str, str | None, str | None]:
    user = str(session.get(SESSION_USER) or "").strip() if has_request_context() else ""
    if user:
        return "office", user[:128], user[:128]
    if not has_request_context():
        return "system", None, None
    path = request.path or ""
    if path.startswith("/api/telegram/"):
        return "telegram_link", None, None
    if path == "/api/work-card/event":
        return "integration_api", None, None
    if path.startswith("/api/auth/"):
        return "auth", None, None
    return "anonymous", None, None


def _store_id_from_request(payload: dict[str, Any] | None = None) -> int | None:
    if not has_request_context():
        return None
    view_args = request.view_args or {}
    for key in ("store_id", "id"):
        raw = view_args.get(key)
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    if payload:
        for key in ("store_id", "id"):
            raw = payload.get(key)
            if raw is not None:
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    pass
    raw = session.get("active_store_id")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def _entity_from_request(payload: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    if not has_request_context():
        return None, None
    view_args = request.view_args or {}
    path = request.path or ""
    if "employee_afm" in view_args:
        return "employee", str(view_args.get("employee_afm") or "")[:128]
    if payload:
        if payload.get("employee_afm"):
            return "employee", str(payload.get("employee_afm"))[:128]
        if payload.get("afm"):
            return "employee", str(payload.get("afm"))[:128]
    if "store_id" in view_args:
        return "store", str(view_args.get("store_id") or "")[:128]
    if path.startswith("/api/store"):
        sid = _store_id_from_request(payload)
        return "store", str(sid) if sid is not None else None
    if path.startswith("/api/telegram/"):
        return "telegram_action", str(view_args.get("token") or "")[:128] or None
    return None, None


def record_audit_event(
    *,
    action: str,
    success: bool | None = None,
    http_status: int | None = None,
    store_id: int | None = None,
    employer_afm: str | None = None,
    branch_aa: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    details: dict[str, Any] | None = None,
    client_ip: str | None = None,
    client_device: str | None = None,
) -> None:
    """Γράφει audit event. Δεν πρέπει ποτέ να σπάει τη βασική λειτουργία."""
    actor_type, actor_name, office_user = _actor_from_request()
    client_ctx = capture_client_context("audit") if has_request_context() else {}
    ip = client_ip or client_ctx.get("client_ip")
    device = client_device or client_ctx.get("client_device")
    if store_id is None and has_request_context():
        store_id = _store_id_from_request()
    if not employer_afm and has_request_context():
        employer_afm = str(session.get("employer_afm") or "").strip() or None
    if not branch_aa and has_request_context():
        branch_aa = str(session.get("branch_aa") or "").strip() or None

    try:
        with cursor() as cur:
            cur.execute(
                """
                INSERT INTO dbo.karta_audit_log (
                    created_at, actor_type, actor_name, office_user,
                    store_id, employer_afm, branch_aa,
                    action, entity_type, entity_id,
                    success, http_status,
                    request_method, request_path, endpoint,
                    client_ip, client_device, details_json
                )
                VALUES (
                    SYSDATETIMEOFFSET(), ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?
                )
                """,
                (
                    actor_type[:32],
                    actor_name,
                    office_user,
                    store_id,
                    (employer_afm or "").strip()[:9] or None,
                    (branch_aa or "").strip()[:32] or None,
                    action[:128],
                    (entity_type or "").strip()[:64] or None,
                    (entity_id or "").strip()[:128] or None,
                    None if success is None else (1 if success else 0),
                    http_status,
                    (request.method if has_request_context() else None),
                    ((request.path or "")[:512] if has_request_context() else None),
                    ((request.endpoint or "")[:256] if has_request_context() else None),
                    (ip or "").strip()[:45] or None,
                    (device or "").strip()[:2000] or None,
                    _json_dumps(_safe_payload(details)),
                ),
            )
    except pyodbc.Error:
        return
    except Exception:
        return


def list_audit_events(
    *,
    store_id: int | None = None,
    kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    from app.row_util import rows_to_dicts

    lim = max(1, min(int(limit or 200), 1000))
    params: list[Any] = [lim]
    filters: list[str] = []
    if store_id is not None:
        filters.append("store_id = ?")
        params.append(int(store_id))
    if kind == "today_notifications":
        filters.append(
            """
            (
                request_path LIKE '/api/telegram/today-hit/%'
                OR request_path LIKE '/api/telegram/today-action/%'
                OR endpoint IN (
                    'telegram.telegram_today_hit_preview',
                    'telegram.telegram_today_hit_confirm',
                    'telegram.telegram_today_action_context',
                    'telegram.telegram_today_action_wto_daily',
                    'telegram.telegram_today_action_snooze',
                    'telegram.telegram_today_action_card',
                    'telegram.telegram_today_action_leave'
                )
            )
            """
        )
    elif kind == "work_card_punches":
        filters.append("action = 'work_card_punch_submit'")
    elif kind == "auth":
        filters.append("action LIKE 'auth.%'")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP (?)
                id, CAST(created_at AS datetime2) AS created_at,
                actor_type, actor_name, office_user,
                store_id, employer_afm, branch_aa,
                action, entity_type, entity_id,
                success, http_status,
                request_method, request_path, endpoint,
                client_ip, client_device, details_json
            FROM dbo.karta_audit_log
            {where}
            ORDER BY created_at DESC, id DESC
            """,
            tuple(params),
        )
        return rows_to_dicts(cur)


def _request_payload() -> dict[str, Any] | None:
    if not has_request_context():
        return None
    try:
        payload = request.get_json(silent=True)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _response_summary(response: Any) -> dict[str, Any] | None:
    try:
        payload = response.get_json(silent=True)
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return None
    summary: dict[str, Any] = {}
    for key in (
        "success",
        "error",
        "id",
        "store_id",
        "count",
        "submission_code",
        "protocol",
        "submit_date",
        "ergani_submission_id",
        "http_status",
        "notify_kind",
        "sent",
        "total",
        "skipped",
    ):
        if key in payload:
            summary[key] = _safe_payload(payload.get(key))
    return summary or None


def _notification_actor_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not has_request_context():
        return None
    path = request.path or ""
    token = ""
    if path.startswith("/api/telegram/today-hit/"):
        token = str((request.view_args or {}).get("token") or "").strip()
    elif path.startswith("/api/telegram/today-action/") and isinstance(payload, dict):
        token = str(payload.get("token") or "").strip()
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
        "name": name or mobile or None,
        "mobile": mobile or None,
        "store_id": row.get("store_id"),
        "store_name": row.get("store_name"),
    }


def register_audit_log(app: Flask) -> None:
    """Κεντρικό audit για όλα τα mutating HTTP requests."""

    @app.before_request
    def _audit_before_request() -> None:
        g.audit_started_at = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
        g.audit_office_user = str(session.get(SESSION_USER) or "").strip() or None

    @app.after_request
    def _audit_after_request(response: Any) -> Any:
        if request.method not in _MUTATING_METHODS:
            return response
        path = request.path or ""
        if path.startswith("/static/"):
            return response
        if path in ("/api/auth/login", "/api/auth/logout"):
            return response

        payload = _request_payload()
        safe_payload = _safe_payload(payload) if payload is not None else None
        entity_type, entity_id = _entity_from_request(payload)
        action = request.endpoint or f"{request.method} {path}"
        details = {
            "started_at": getattr(g, "audit_started_at", None),
            "query": _safe_payload(request.args.to_dict(flat=False)),
            "view_args": _safe_payload(request.view_args or {}),
            "request": safe_payload,
            "response": _response_summary(response),
        }
        notification_actor = _notification_actor_from_payload(payload)
        if notification_actor:
            details["notification_actor"] = notification_actor
        record_audit_event(
            action=str(action),
            success=200 <= int(response.status_code or 0) < 400,
            http_status=int(response.status_code or 0),
            store_id=_store_id_from_request(payload),
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        return response
