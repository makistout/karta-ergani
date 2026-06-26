from __future__ import annotations

import json
from typing import Any, Callable

from flask import current_app, request, session


def bearer_from_request() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    tok = session.get("ergani_bearer")
    return str(tok).strip() if tok else None


def _iso_dt(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def active_store_payload(ctx: dict[str, Any]) -> dict[str, Any]:
    """JSON payload για GET /api/store/active — χωρίς επιπλέον query."""
    return {
        "id": ctx["id"],
        "name": ctx["name"],
        "employer_afm": ctx["employer_afm"],
        "branch_aa": ctx["branch_aa"],
        "ergani_env": ctx.get("ergani_env"),
        "ergani_env_label": ctx.get("ergani_env_label"),
        "api_base_url": ctx.get("api_base_url"),
        "portal_base_url": ctx.get("portal_base_url"),
        "schedule_last_sync_at": ctx.get("schedule_last_sync_at"),
        "work_log_last_sync_at": ctx.get("work_log_last_sync_at"),
        "sync_meta_columns": ctx.get("sync_meta_columns"),
    }


def resolve_active_store(*, refresh_session: bool = True) -> dict[str, Any] | None:
    """Ενεργό κατάστημα από session + DB (συμπληρώνει employer_afm αν λείπει)."""
    sid = session.get("active_store_id")
    if not sid:
        return None
    from app import repo_store as repo

    cfg = repo.get_store_config(int(sid))
    if not cfg:
        for key in (
            "active_store_id",
            "ergani_bearer",
            "employer_afm",
            "branch_aa",
            "ergani_env",
        ):
            session.pop(key, None)
        return None
    from app.ergani_env import store_api_context

    ctx = store_api_context(cfg)
    ctx["schedule_last_sync_at"] = _iso_dt(repo.effective_schedule_sync_at(cfg))
    ctx["work_log_last_sync_at"] = _iso_dt(repo.effective_work_log_sync_at(cfg))
    ctx["sync_meta_columns"] = repo.sync_meta_columns_available()
    old_env = session.get("ergani_env")
    bearer_store_id = session.get("ergani_bearer_store_id")
    if refresh_session:
        session["employer_afm"] = ctx["employer_afm"]
        session["branch_aa"] = ctx["branch_aa"]
        session["ergani_env"] = ctx["ergani_env"]
    if old_env and old_env != ctx["ergani_env"]:
        session.pop("ergani_bearer", None)
        session.pop("ergani_bearer_store_id", None)
        session.pop("ergani_bearer_env", None)
    elif bearer_store_id and str(bearer_store_id) != str(ctx["id"]):
        session.pop("ergani_bearer", None)
        session.pop("ergani_bearer_store_id", None)
        session.pop("ergani_bearer_env", None)
    return ctx


def active_store_from_session() -> dict[str, str | int] | None:
    ctx = resolve_active_store()
    if not ctx:
        return None
    return {
        "id": ctx["id"],
        "employer_afm": ctx["employer_afm"],
        "branch_aa": ctx["branch_aa"],
    }


def ensure_ergani_bearer(ctx: dict[str, Any]) -> str | None:
    """Bearer από session ή επανασύνδεση με credentials καταστήματος."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    token = str(session.get("ergani_bearer") or "").strip()
    token_store_id = str(session.get("ergani_bearer_store_id") or "").strip()
    token_env = str(session.get("ergani_bearer_env") or "").strip()
    ctx_store_id = str(ctx.get("id") or "").strip()
    ctx_env = str(ctx.get("ergani_env") or "production").strip()
    if token and token_store_id == ctx_store_id and token_env == ctx_env:
        return token
    from app.ergani_client import ErganiClient

    from app.ergani_env import api_login_credentials

    client = ErganiClient(ctx.get("api_base_url"))
    api_user, api_pwd, api_ut = api_login_credentials(ctx)
    resp = client.authenticate(api_user, api_pwd, api_ut)
    payload = json_or_text(resp)
    if not resp.ok or not isinstance(payload, dict) or not payload.get("accessToken"):
        return None
    token = str(payload["accessToken"])
    session["ergani_bearer"] = token
    session["ergani_bearer_store_id"] = ctx_store_id
    session["ergani_bearer_env"] = ctx_env
    session["ergani_env"] = ctx.get("ergani_env") or "production"
    return token


def json_or_text(resp) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text


def response_body_text(resp) -> str | None:
    try:
        return resp.text
    except Exception:
        return None


def persist_safe(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    try:
        fn(*args, **kwargs)
    except Exception:
        current_app.logger.exception("Αποτυχία τοπικής αποθήκευσης στη βάση ergani-karta")
