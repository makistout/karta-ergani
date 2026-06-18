from flask import Flask, jsonify

from config import Config
from app.routes_employees import employees_bp
from app.routes_schedule import schedule_bp
from app.routes_work_log import work_log_bp
from app.routes_dashboard import dashboard_bp
from app.routes_ergani import ergani_bp
from app.routes_local import local_bp
from app.routes_store import store_bp
from app.routes_sync import sync_bp
from app.routes_period_sync import period_sync_bp
from app.routes_sync_log import sync_log_bp
from app.routes_ui import register_ui_redirects, ui_bp
from app.routes_leave import leave_bp
from app.routes_monthly_status import monthly_status_bp
from app.routes_telegram import telegram_bp
from app.routes_auth import auth_bp
from app.routes_work_card import work_card_bp


def create_app() -> Flask:
    Config.validate_for_startup()
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY
    app.url_map.strict_slashes = False

    from app.security import register_security

    register_security(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(work_card_bp)
    app.register_blueprint(leave_bp)
    app.register_blueprint(local_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(ergani_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(period_sync_bp)
    app.register_blueprint(sync_log_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(work_log_bp)
    app.register_blueprint(monthly_status_bp)
    app.register_blueprint(telegram_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(ui_bp)
    register_ui_redirects(app)

    @app.get("/api")
    def api_index():
        return jsonify({
            "service": "karta-ergani",
            "database": Config.DB_DATABASE,
            "ui": "/ui/",
            "stores": "/api/store/",
            "ergani": "/api/ergani/",
            "employees": "/api/employees/list",
            "schedule": "/api/schedule/list",
            "work_log": "/api/work-log/list",
            "monthly_status": "/api/monthly-status/list",
            "monthly_status_sync": "POST /api/monthly-status/sync",
            "telegram_webhook": "POST /api/telegram/webhook",
            "telegram_test": "POST /api/telegram/test/<store_id>",
            "telegram_notify_missing": "POST /api/telegram/notify/missing-punch",
            "dashboard_card_report": "/api/dashboard/card-report",
            "sync": "POST /api/ergani/sync-all",
            "work_card": "/api/work-card/",
            "work_card_list": "GET /api/work-card/list",
            "work_card_submit": "POST /api/work-card/submit",
            "leave_types": "GET /api/leave/types",
            "leave_submit": "POST /api/leave/submit",
            "local": "/api/local/",
            "health": "/api/local/health",
        })

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "database": Config.DB_DATABASE})

    @app.get("/favicon.ico")
    def favicon():
        return app.send_static_file("favicon.ico")

    return app
