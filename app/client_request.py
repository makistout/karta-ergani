"""IP και στοιχεία συσκευής από HTTP request (audit χτυπημάτων κάρτας)."""

from __future__ import annotations

import json
import ipaddress
from typing import Any

from flask import Request, has_request_context, request


def _clean_ip(value: str | None) -> str | None:
    raw = str(value or "").strip().strip("\"'")
    if not raw:
        return None
    if raw.startswith("[") and "]" in raw:
        raw = raw[1:raw.index("]")]
    elif ":" in raw and raw.count(":") == 1 and "." in raw:
        raw = raw.split(":", 1)[0].strip()
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        return None
    return raw[:45]


def _ips_from_header(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    out: list[str] = []
    for part in raw.split(","):
        ip = _clean_ip(part)
        if ip:
            out.append(ip)
    return out


def _forwarded_header_ip(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for part in raw.split(";"):
        key, sep, val = part.partition("=")
        if sep and key.strip().lower() == "for":
            return _clean_ip(val.strip())
    return None


def _is_loopback_ip(value: str | None) -> bool:
    try:
        return bool(value) and ipaddress.ip_address(str(value)).is_loopback
    except ValueError:
        return False


def _is_private_or_loopback(value: str | None) -> bool:
    try:
        addr = ipaddress.ip_address(str(value))
    except ValueError:
        return True
    return bool(addr.is_loopback or addr.is_private or addr.is_link_local)


def _pick_best_ip(candidates: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    """Προτιμά δημόσια IP· αλλιώς ιδιωτική· αλλιώς loopback."""
    public: tuple[str, str] | None = None
    private: tuple[str, str] | None = None
    loopback: tuple[str, str] | None = None
    for ip, source in candidates:
        if _is_loopback_ip(ip):
            if loopback is None:
                loopback = (ip, source)
            continue
        if _is_private_or_loopback(ip):
            if private is None:
                private = (ip, source)
            continue
        if public is None:
            public = (ip, source)
    if public:
        return public
    if private:
        return private
    if loopback:
        return loopback
    return None, None


def _client_ip_info(req: Request) -> tuple[str | None, str | None]:
    """Επιστρέφει (ip, πηγή header). Αγνοεί 127.0.0.1 όταν υπάρχει καλύτερη IP."""
    header_candidates = (
        ("CF-Connecting-IP", req.headers.get("CF-Connecting-IP")),
        ("True-Client-IP", req.headers.get("True-Client-IP")),
        ("X-ARR-ClientIP", req.headers.get("X-ARR-ClientIP")),
        ("X-Real-IP", req.headers.get("X-Real-IP")),
        ("X-Client-IP", req.headers.get("X-Client-IP")),
        ("X-Original-For", req.headers.get("X-Original-For")),
        ("X-Forwarded-For", req.headers.get("X-Forwarded-For")),
    )
    scored: list[tuple[str, str]] = []
    for source, raw in header_candidates:
        if source == "X-Forwarded-For":
            for ip in _ips_from_header(raw):
                scored.append((ip, source))
        else:
            ip = _clean_ip(raw)
            if ip:
                scored.append((ip, source))

    forwarded_ip = _forwarded_header_ip(req.headers.get("Forwarded"))
    if forwarded_ip:
        scored.append((forwarded_ip, "Forwarded"))

    # WSGI/IIS environ fallbacks (μετά από rewrite κανόνες).
    for env_key, source in (
        ("HTTP_X_FORWARDED_FOR", "environ:X-Forwarded-For"),
        ("HTTP_X_REAL_IP", "environ:X-Real-IP"),
        ("HTTP_X_ARR_CLIENTIP", "environ:X-ARR-ClientIP"),
        ("HTTP_CLIENT_IP", "environ:CLIENT_IP"),
    ):
        raw = req.environ.get(env_key)
        if not raw:
            continue
        if "FORWARDED_FOR" in env_key:
            for ip in _ips_from_header(str(raw)):
                scored.append((ip, source))
        else:
            ip = _clean_ip(str(raw))
            if ip:
                scored.append((ip, source))

    remote = _clean_ip(req.remote_addr)
    if remote:
        scored.append((remote, "remote_addr"))

    return _pick_best_ip(scored)


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
    client_ip, ip_source = _client_ip_info(req)
    details["ip_source"] = ip_source
    remote_addr = _clean_ip(req.remote_addr)
    if remote_addr and (_is_loopback_ip(remote_addr) or remote_addr != client_ip):
        details["remote_addr"] = remote_addr
    forwarded_for = (req.headers.get("X-Forwarded-For") or "").strip()[:512]
    if forwarded_for:
        details["x_forwarded_for"] = forwarded_for
    arr_client_ip = (req.headers.get("X-ARR-ClientIP") or "").strip()[:128]
    if arr_client_ip:
        details["x_arr_clientip"] = arr_client_ip
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
        "client_ip": client_ip,
        "client_device": device_json,
    }


def observed_peer_ip(req: Request | None = None) -> str | None:
    """Trusted edge/TCP peer IP used as network evidence; ignores X-Forwarded-For."""
    if req is None:
        if not has_request_context():
            return None
        req = request
    return _clean_ip(req.headers.get("X-ARR-ClientIP")) or _clean_ip(req.remote_addr)
