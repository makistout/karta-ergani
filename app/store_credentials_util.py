"""Βοηθητικά για διαπιστευτήρια καταστήματος (admin API vs web portal)."""

from __future__ import annotations

from typing import Any

MASKED = "********"


def is_masked(value: str | None) -> bool:
    return (value or "").strip() == MASKED


def merge_secret(new_value: str | None, existing: dict[str, Any] | None, key: str) -> str:
    raw = (new_value or "").strip()
    if not raw or raw == MASKED:
        return str((existing or {}).get(key) or "")
    return raw


def mask_store_secrets(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("password", "web_password"):
        if out.get(key):
            out[key] = MASKED
    return out
