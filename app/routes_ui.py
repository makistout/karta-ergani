"""Σερβίρισμα ξεχωριστών HTML σελίδων UI."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, redirect, send_from_directory

ui_bp = Blueprint("ui", __name__, url_prefix="/ui")
_UI_DIR = Path(__file__).resolve().parent / "static" / "ui"


@ui_bp.after_request
def _ui_no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@ui_bp.get("/")
def ui_home():
    return send_from_directory(_UI_DIR, "home.html")


@ui_bp.get("/login")
def ui_login():
    return send_from_directory(_UI_DIR, "login.html")


@ui_bp.get("/stores")
def ui_stores_list():
    return send_from_directory(_UI_DIR, "stores-list.html")


@ui_bp.get("/stores/credentials")
def ui_store_credentials():
    return send_from_directory(_UI_DIR, "store-credentials.html")


@ui_bp.get("/store/edit/<int:store_id>")
def ui_store_edit_redirect(store_id: int):
    """Συμβατότητα με URL /ui/store/edit/<id> → διαπιστευτήρια."""
    return redirect(f"/ui/stores/credentials?edit=1&id={store_id}")


@ui_bp.get("/stores/branch")
def ui_store_branch():
    return send_from_directory(_UI_DIR, "store-branch.html")


@ui_bp.get("/stores/mappings")
def ui_store_mappings():
    return send_from_directory(_UI_DIR, "store-mappings.html")


@ui_bp.get("/employees")
def ui_employees_list():
    return send_from_directory(_UI_DIR, "employees-list.html")


@ui_bp.get("/schedule")
def ui_schedule_list():
    return send_from_directory(_UI_DIR, "schedule-list.html")


@ui_bp.get("/work-log")
def ui_work_log_list():
    return send_from_directory(_UI_DIR, "work-log-list.html")


@ui_bp.get("/work-log/history")
def ui_work_log_history():
    return send_from_directory(_UI_DIR, "work-log-history.html")


@ui_bp.get("/missing-cards")
def ui_missing_cards():
    return send_from_directory(_UI_DIR, "missing-cards-list.html")


@ui_bp.get("/monthly-status")
def ui_monthly_status():
    return send_from_directory(_UI_DIR, "monthly-status-list.html")


@ui_bp.get("/work-card")
def ui_work_card():
    return send_from_directory(_UI_DIR, "work-card-list.html")


@ui_bp.get("/telegram-hit")
def ui_telegram_hit():
    return send_from_directory(_UI_DIR, "telegram-hit.html")


@ui_bp.get("/telegram-punch")
def ui_telegram_punch_redirect():
    """Παλιός σύνδεσμος → telegram-hit."""
    return redirect("/ui/telegram-hit")


@ui_bp.get("/retro-hit")
def ui_retro_hit():
    return send_from_directory(_UI_DIR, "retro-hit.html")


@ui_bp.get("/retro-punch")
def ui_retro_punch_redirect():
    """Παλιός σύνδεσμος → retro-hit."""
    return redirect("/ui/retro-hit")


@ui_bp.get("/today-hit")
def ui_today_hit():
    return send_from_directory(_UI_DIR, "today-hit.html")


@ui_bp.get("/today-action")
def ui_today_action():
    return send_from_directory(_UI_DIR, "today-action.html")


@ui_bp.get("/sync")
def ui_sync_hub():
    return send_from_directory(_UI_DIR, "sync-hub.html")


@ui_bp.get("/sync-log")
def ui_sync_log():
    return send_from_directory(_UI_DIR, "sync-log-list.html")


def register_ui_redirects(app):
    @app.get("/")
    def root_redirect():
        return redirect("/ui/")
