"""Κρυπτογράφηση PIN λήπτη ειδοποιήσεων (χωρίς plaintext στη βάση)."""

from __future__ import annotations

import hashlib
import re
import secrets

from config import Config

_PIN_MASK = "********"
_PIN_RE = re.compile(r"^\d{4}$")


def pin_mask() -> str:
    return _PIN_MASK


def is_pin_mask(value: str | None) -> bool:
    return str(value or "").strip() == _PIN_MASK


def is_valid_notify_pin(pin: str | None) -> bool:
    return bool(_PIN_RE.fullmatch(str(pin or "").strip()))


def validate_notify_pin(pin: str | None) -> str:
    """Επιστρέφει κανονικοποιημένο 4ψήφιο PIN ή ValueError."""
    value = str(pin or "").strip()
    if not is_valid_notify_pin(value):
        raise ValueError("Ο PIN πρέπει να είναι ακριβώς 4 αριθμητικά ψηφία")
    return value


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
