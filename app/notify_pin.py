"""Κρυπτογράφηση PIN λήπτη ειδοποιήσεων (χωρίς plaintext στη βάση)."""

from __future__ import annotations

import hashlib
import secrets

from config import Config

_PIN_MASK = "********"


def pin_mask() -> str:
    return _PIN_MASK


def is_pin_mask(value: str | None) -> bool:
    return str(value or "").strip() == _PIN_MASK


def hash_notify_pin(*, store_id: int, mobile: str, pin: str) -> str:
    secret = (Config.SECRET_KEY or "karta-ergani-dev-only-not-for-production").strip()
    raw = f"{secret}|{int(store_id)}|{mobile}|{str(pin).strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def verify_notify_pin(
    *,
    store_id: int,
    mobile: str,
    pin: str,
    pin_hash: str | None,
) -> bool:
    stored = (pin_hash or "").strip()
    if not stored or not str(pin or "").strip():
        return False
    candidate = hash_notify_pin(store_id=store_id, mobile=mobile, pin=str(pin).strip())
    return secrets.compare_digest(candidate, stored)
