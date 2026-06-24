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


def verify_notify_pin_for_recipient(
    *,
    store_id: int,
    mobile: str | None,
    pin: str,
    pin_hash: str | None,
    pin_plain: str | None = None,
) -> bool:
    """Επαλήθευση PIN — hash με κανονικοποιημένο/ωμό mobile ή plaintext fallback."""
    from app.repo_notify_recipients import normalize_mobile

    entered = str(pin or "").strip()
    if not entered or not is_valid_notify_pin(entered):
        return False

    stored_hash = (pin_hash or "").strip()
    mobile_candidates: list[str] = []
    norm = normalize_mobile(mobile)
    if norm:
        mobile_candidates.append(norm)
    raw_digits = re.sub(r"\D", "", str(mobile or ""))
    if raw_digits and raw_digits not in mobile_candidates:
        mobile_candidates.append(raw_digits)
    if "" not in mobile_candidates:
        mobile_candidates.append("")

    for mob in mobile_candidates:
        if stored_hash and verify_notify_pin(
            store_id=store_id,
            mobile=mob,
            pin=entered,
            pin_hash=stored_hash,
        ):
            return True

    plain = str(pin_plain or "").strip()
    return bool(plain and is_valid_notify_pin(plain) and secrets.compare_digest(plain, entered))
