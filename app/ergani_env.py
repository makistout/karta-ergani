"""
Περιβάλλον Ergani ανά κατάστημα (παραγωγή / δοκιμαστικό).

Δοκιμαστικό (ergani_env=trial): **όλα** στο trialv2eservices.yeka.gr
  - REST API: …/WebservicesAPI/Api/
  - Portal parse (ωράριο, πραγματική): https://trialv2eservices.yeka.gr/

Παραγωγή: **όλα** στο eservices.yeka.gr (ίδια διαχωριστικά paths).
"""

from __future__ import annotations

from typing import Any

from config import Config

ERGANI_ENV_PRODUCTION = "production"
ERGANI_ENV_TRIAL = "trial"

URL_PRODUCTION = "https://eservices.yeka.gr/WebservicesAPI/Api/"
URL_TRIAL = "https://trialv2eservices.yeka.gr/WebservicesAPI/Api/"

PORTAL_BASE_PRODUCTION = "https://eservices.yeka.gr/"
PORTAL_BASE_TRIAL = "https://trialv2eservices.yeka.gr/"


def normalize_ergani_env(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v in (ERGANI_ENV_TRIAL, "trialv2", "test", "δοκιμαστικό"):
        return ERGANI_ENV_TRIAL
    return ERGANI_ENV_PRODUCTION


def base_url_for_env(env: str | None) -> str:
    if normalize_ergani_env(env) == ERGANI_ENV_TRIAL:
        return URL_TRIAL
    return URL_PRODUCTION


def portal_base_for_env(env: str | None) -> str:
    """Web portal parse (ωράριο / πραγματική) — όχι REST API."""
    if normalize_ergani_env(env) == ERGANI_ENV_TRIAL:
        return PORTAL_BASE_TRIAL
    return PORTAL_BASE_PRODUCTION


def portal_base_from_ctx(ctx: dict[str, Any] | None) -> str:
    if ctx:
        base = str(ctx.get("portal_base_url") or "").strip()
        if base:
            return base if base.endswith("/") else base + "/"
        env = ctx.get("ergani_env")
        if env:
            return portal_base_for_env(env)
    return PORTAL_BASE_PRODUCTION


def env_label(env: str | None) -> str:
    return "Δοκιμαστικό" if normalize_ergani_env(env) == ERGANI_ENV_TRIAL else "Παραγωγή"


def _env_from_session() -> str | None:
    try:
        from flask import has_request_context, session

        if has_request_context():
            return session.get("ergani_env")
    except RuntimeError:
        pass
    return None


def ergani_env_from_request(data: dict[str, Any] | None = None) -> str:
    raw = None
    if data:
        raw = data.get("ergani_env") or data.get("erganiEnv")
    if not raw:
        raw = request_header_env()
    if not raw:
        raw = _env_from_session()
    return normalize_ergani_env(raw)


def base_url_from_request(data: dict[str, Any] | None = None) -> str:
    return base_url_for_env(ergani_env_from_request(data))


def portal_base_from_request(data: dict[str, Any] | None = None) -> str:
    return portal_base_for_env(ergani_env_from_request(data))


def request_header_env() -> str | None:
    from flask import request

    return request.headers.get("X-Ergani-Env") or request.args.get("ergani_env")


def api_login_credentials(cfg: dict[str, Any]) -> tuple[str, str, str]:
    """Ergani API — αποκλειστικά web user (usertype 02)."""
    user = str(cfg.get("web_username") or "").strip()
    pwd = str(cfg.get("web_password") or "").strip()
    if not user or not pwd:
        raise ValueError(
            "Λείπουν διαπιστευτήρια web (API) — συμπληρώστε web username/password στο κατάστημα"
        )
    return user, pwd, "02"


def portal_login_credentials(cfg: dict[str, Any]) -> tuple[str, str, str]:
    """Portal eservices — αποκλειστικά admin (π.χ. EFKA, usertype 01)."""
    user = str(cfg.get("username") or "").strip()
    pwd = str(cfg.get("password") or "").strip()
    ut = str(cfg.get("usertype") or "01").strip()
    if not user or not pwd:
        raise ValueError(
            "Λείπουν διαπιστευτήρια admin (portal) — συμπληρώστε admin username/password"
        )
    return user, pwd, ut


def store_api_context(cfg: dict[str, Any]) -> dict[str, Any]:
    env = normalize_ergani_env(cfg.get("ergani_env"))
    return {
        "id": int(cfg["id"]),
        "name": cfg["name"],
        "employer_afm": cfg["employer_afm"],
        "branch_aa": cfg.get("branch_aa") or "0",
        "username": cfg.get("username"),
        "password": cfg.get("password"),
        "usertype": cfg.get("usertype") or "01",
        "web_username": cfg.get("web_username"),
        "web_password": cfg.get("web_password"),
        "ergani_env": env,
        "api_base_url": base_url_for_env(env),
        "portal_base_url": portal_base_for_env(env),
        "ergani_env_label": env_label(env),
    }


def client_for_store(cfg: dict[str, Any]):
    from app.ergani_client import ErganiClient

    return ErganiClient(store_api_context(cfg)["api_base_url"])
