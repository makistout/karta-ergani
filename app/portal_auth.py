"""Έλεγχος διαπιστευτηρίων: web → API, admin → portal."""

from __future__ import annotations

from typing import Any

import requests

from app.ergani_client import ErganiClient
from app.ergani_env import base_url_for_env, normalize_ergani_env
from app.portal_schedule_sync import _login_session


def verify_web_api(
    web_username: str,
    web_password: str,
    *,
    ergani_env: str = "production",
) -> None:
    user = (web_username or "").strip()
    pwd = web_password or ""
    if not user or not pwd:
        raise ValueError("Υποχρεωτικά web username και password (API)")
    client = ErganiClient(base_url_for_env(normalize_ergani_env(ergani_env)))
    resp = client.authenticate(user, pwd, "02")
    if not resp.ok:
        raise RuntimeError(
            "Αποτυχία Ergani API με web user — ελέγξτε web username/password"
        )


def verify_admin_portal(
    admin_username: str,
    admin_password: str,
    admin_usertype: str = "01",
    *,
    ergani_env: str = "production",
) -> None:
    user = (admin_username or "").strip()
    pwd = admin_password or ""
    ut = (admin_usertype or "01").strip()
    if not user or not pwd:
        raise ValueError("Υποχρεωτικά admin username και password (portal)")
    env = normalize_ergani_env(ergani_env)
    from app.ergani_env import portal_base_for_env

    ctx = {
        "username": user,
        "password": pwd,
        "usertype": ut,
        "ergani_env": env,
        "portal_base_url": portal_base_for_env(env),
    }
    _login_session(ctx)


def verify_store_wizard(
    *,
    web_username: str,
    web_password: str,
    admin_username: str,
    admin_password: str,
    admin_usertype: str = "01",
    ergani_env: str = "production",
) -> dict[str, Any]:
    """Βήμα 1 wizard: web → API, admin → portal."""
    wu = (web_username or "").strip()
    au = (admin_username or "").strip()
    verify_web_api(wu, web_password, ergani_env=ergani_env)
    verify_admin_portal(au, admin_password, admin_usertype, ergani_env=ergani_env)
    return {
        "success": True,
        "web_user": wu,
        "admin_user": au,
        "api_mode": "web",
        "portal_mode": "admin",
    }
