"""Δημόσιοι σύνδεσμοι εφαρμογής (Telegram, Email, redirects browser)."""

from __future__ import annotations

from urllib.parse import quote

from config import Config

_PROD_FALLBACK = "https://erganios.gr"


def effective_public_base_url() -> str:
    """
    Βάση για σύνδεσμους σε εξωτερικά κανάλια (Telegram/Email).
    Σε production αγνοεί λανθασμένο localhost στο .env.
    """
    base = (Config.PUBLIC_BASE_URL or _PROD_FALLBACK).strip().rstrip("/")
    lower = base.lower()
    if not Config.FLASK_DEBUG and (
        "localhost" in lower or "127.0.0.1" in lower
    ):
        return _PROD_FALLBACK
    return base or _PROD_FALLBACK


def ui_relative_path(ui_path: str, *, token: str | None = None) -> str:
    """Σχετική διαδρομή UI — ίδιο origin με το browser (μετά PIN)."""
    path = ui_path if ui_path.startswith("/") else f"/{ui_path}"
    t = (token or "").strip()
    if t:
        return f"{path}?t={quote(t, safe='')}"
    return path


def ui_public_url(ui_path: str, *, token: str | None = None) -> str:
    """Απόλυτος σύνδεσμος για Telegram/Email."""
    rel = ui_relative_path(ui_path, token=token)
    return f"{effective_public_base_url()}{rel}"
