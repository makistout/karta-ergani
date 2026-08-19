"""Σερβίρισμα ξεχωριστών HTML σελίδων UI."""

from __future__ import annotations

from flask import Blueprint, redirect, render_template

from app.landing_seo import LANDING_HOME_PATH, SEO_PAGES
from app.public_urls import effective_public_base_url

ui_bp = Blueprint("ui", __name__, url_prefix="/ui")

_LANDING_CANONICAL_PATH = LANDING_HOME_PATH


def _landing_context() -> dict[str, object]:
    base = effective_public_base_url().rstrip("/")
    return {
        "canonical_url": f"{base}{_LANDING_CANONICAL_PATH}",
        "landing_home_url": _LANDING_CANONICAL_PATH,
        "contact_url": f"{_LANDING_CANONICAL_PATH}#contact",
        "seo_guides": [
            {
                "slug": str(p["slug"]),
                "label": str(p["nav_label"]),
                "url": f"/{p['slug']}/",
            }
            for p in SEO_PAGES
        ],
    }


def _render_landing():
    return render_template("ui/landing.html", **_landing_context())


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
    return redirect(_LANDING_CANONICAL_PATH, code=301)


@ui_bp.get("/login")
def ui_login():
    return render_template("ui/login.html")


@ui_bp.get("/verify-email")
def ui_verify_email():
    return render_template("ui/verify-email.html")


@ui_bp.get("/forgot-password")
def ui_forgot_password():
    return render_template("ui/forgot-password.html")


@ui_bp.get("/reset-password")
def ui_reset_password():
    return render_template("ui/reset-password.html")


@ui_bp.get("/change-password")
def ui_change_password():
    return render_template("ui/change-password.html")


@ui_bp.get("/accept-terms")
def ui_accept_terms():
    return render_template("ui/accept-terms.html")


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


@ui_bp.get("/employees/contracts")
def ui_employees_contracts():
    return render_template("ui/employees-contracts.html")


@ui_bp.get("/employees/detail")
def ui_employee_detail():
    return render_template("ui/employee-detail.html")


@ui_bp.get("/employees/weekly-schedule")
def ui_employee_weekly_schedule():
    return render_template("ui/employee-weekly-schedule.html")


@ui_bp.get("/employees/monthly-overview")
def ui_employee_monthly_overview():
    return render_template("ui/employee-monthly-overview.html")


@ui_bp.get("/schedule")
def ui_schedule_list():
    return render_template("ui/schedule-list.html")


@ui_bp.get("/work-log")
def ui_work_log_list():
    return render_template("ui/work-log-list.html")


@ui_bp.get("/protocols")
def ui_protocols_list():
    return render_template("ui/protocols-list.html")


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


@ui_bp.get("/apologistic")
def ui_apologistic():
    return render_template("ui/apologistic.html")


@ui_bp.get("/apologistic/timekeeping")
def ui_apologistic_timekeeping():
    return render_template("ui/apologistic-timekeeping.html")


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
    def root_landing():
        return _render_landing()

    @app.get("/psifiaki-karta-ergasias")
    @app.get("/psifiaki-karta-ergasias/")
    def landing_seo():
        return redirect("/", code=301)
