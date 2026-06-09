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
from app.routes_sync_log import sync_log_bp
from app.routes_ui import register_ui_redirects, ui_bp
from app.routes_leave import leave_bp
from app.routes_work_card import work_card_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.secret_key = Config.SECRET_KEY
    app.url_map.strict_slashes = False
    app.register_blueprint(work_card_bp)
    app.register_blueprint(leave_bp)
    app.register_blueprint(local_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(ergani_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(sync_log_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(schedule_bp)
    app.register_blueprint(work_log_bp)
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

    return app
