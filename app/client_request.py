"""IP και στοιχεία συσκευής από HTTP request (audit χτυπημάτων κάρτας)."""

from __future__ import annotations

import json
from typing import Any

from flask import Request, has_request_context, request


def _client_ip(req: Request) -> str | None:
    forwarded = (req.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        ip = forwarded.split(",")[0].strip()
        if ip:
            return ip[:45]
    real_ip = (req.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip[:45]
    remote = (req.remote_addr or "").strip()
    return remote[:45] if remote else None


def capture_client_context(
    source: str,
    *,
    extra: dict[str, Any] | None = None,
    req: Request | None = None,
) -> dict[str, str | None]:
    """Επιστρέφει client_ip και client_device (JSON) για αποθήκευση στη βάση."""
    if req is None:
        if not has_request_context():
            return {"client_ip": None, "client_device": None}
        req = request

    details: dict[str, Any] = {
        "source": (source or "").strip()[:32] or None,
        "user_agent": (req.headers.get("User-Agent") or "").strip()[:512] or None,
        "accept_language": (req.headers.get("Accept-Language") or "").strip()[:128] or None,
        "sec_ch_ua": (req.headers.get("Sec-CH-UA") or "").strip()[:256] or None,
        "sec_ch_ua_mobile": (req.headers.get("Sec-CH-UA-Mobile") or "").strip()[:16] or None,
        "sec_ch_ua_platform": (req.headers.get("Sec-CH-UA-Platform") or "").strip()[:64] or None,
        "referer": (req.headers.get("Referer") or "").strip()[:512] or None,
    }
    if extra:
        for key, value in extra.items():
            if value is not None and str(value).strip():
                details[str(key)[:64]] = value

    body_extra: dict[str, Any] | None = None
    if req.method in ("POST", "PUT", "PATCH"):
        try:
            payload = req.get_json(silent=True)
            if isinstance(payload, dict) and isinstance(payload.get("device_info"), dict):
                body_extra = payload["device_info"]
        except Exception:
            body_extra = None
    if body_extra:
        for key, value in body_extra.items():
            if value is not None and str(value).strip():
                details[f"client_{key}"] = value

    device_json = json.dumps(details, ensure_ascii=False)
    if len(device_json) > 2000:
        device_json = device_json[:2000]
    return {
        "client_ip": _client_ip(req),
        "client_device": device_json,
    }
