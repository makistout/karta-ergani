"""Σερβίρισμα ξεχωριστών HTML σελίδων UI."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template

ui_bp = Blueprint("ui", __name__, url_prefix="/ui")


@ui_bp.after_request
def _ui_no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@ui_bp.get("/")
def ui_home():
    return render_template("ui/home.html")


@ui_bp.get("/landing")
def ui_landing():
    return render_template("ui/landing.html")


@ui_bp.get("/login")
def ui_login():
    return render_template("ui/login.html")


@ui_bp.get("/stores")
def ui_stores_list():
    return render_template("ui/stores-list.html")


@ui_bp.get("/stores/credentials")
def ui_store_credentials():
    return render_template("ui/store-credentials.html")


@ui_bp.get("/stores/notify")
def ui_store_notify():
    return render_template("ui/store-notify.html")


@ui_bp.get("/store/edit/<int:store_id>")
def ui_store_edit_redirect(store_id: int):
    """Συμβατότητα με URL /ui/store/edit/<id> → διαπιστευτήρια."""
    return redirect(f"/ui/stores/credentials?edit=1&id={store_id}")


@ui_bp.get("/stores/branch")
def ui_store_branch():
    return render_template("ui/store-branch.html")


@ui_bp.get("/stores/mappings")
def ui_store_mappings():
    return render_template("ui/store-mappings.html")


@ui_bp.get("/employees")
def ui_employees_list():
    return render_template("ui/employees-list.html")


@ui_bp.get("/employees/weekly-schedule")
def ui_employee_weekly_schedule():
    return render_template("ui/employee-weekly-schedule.html")


@ui_bp.get("/schedule")
def ui_schedule_list():
    return render_template("ui/schedule-list.html")


@ui_bp.get("/work-log")
def ui_work_log_list():
    return render_template("ui/work-log-list.html")


@ui_bp.get("/work-log/history")
def ui_work_log_history():
    return render_template("ui/work-log-history.html")


@ui_bp.get("/missing-cards")
def ui_missing_cards():
    return render_template("ui/missing-cards-list.html")


@ui_bp.get("/missing-cards/close-all")
def ui_missing_cards_close_all():
    return render_template("ui/missing-cards-close-all.html")


@ui_bp.get("/monthly-status")
def ui_monthly_status():
    return render_template("ui/monthly-status-list.html")


@ui_bp.get("/work-card")
def ui_work_card():
    return render_template("ui/work-card-list.html")


@ui_bp.get("/telegram-hit")
def ui_telegram_hit():
    return render_template("ui/telegram-hit.html")


@ui_bp.get("/telegram-punch")
def ui_telegram_punch_redirect():
    """Παλιός σύνδεσμος → telegram-hit."""
    return redirect("/ui/telegram-hit")


@ui_bp.get("/retro-hit")
def ui_retro_hit():
    return render_template("ui/retro-hit.html")


@ui_bp.get("/retro-punch")
def ui_retro_punch_redirect():
    """Παλιός σύνδεσμος → retro-hit."""
    return redirect("/ui/retro-hit")


@ui_bp.get("/today-hit")
def ui_today_hit():
    return render_template("ui/today-hit.html")


@ui_bp.get("/today-action")
def ui_today_action():
    return render_template("ui/today-action.html")


@ui_bp.get("/sync")
def ui_sync_hub():
    return render_template("ui/sync-hub.html")


@ui_bp.get("/sync-log")
def ui_sync_log():
    return render_template("ui/sync-log-list.html")


@ui_bp.get("/users")
def ui_users():
    return render_template("ui/users-list.html")


def register_ui_redirects(app):
    @app.get("/")
    def root_redirect():
        return redirect("/ui/")
