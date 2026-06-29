from flask import Flask, render_template_string
import pytest
from unittest.mock import patch

from app.access_control import (
    SESSION_PERMISSIONS,
    SESSION_ROLE,
    SESSION_SUPER_ADMIN,
    normalize_role,
    permission_for_path,
    permissions_for_role,
    register_access_context,
)
from app.office_auth import register_login_guard
from app.office_auth import SESSION_LOGGED_IN, SESSION_USER
from app.routes_auth import auth_bp
from app.routes_users import users_bp
from app.routes_work_log import work_log_bp
from app.work_card_payload import tz_athens
from config import Config
from datetime import datetime, timedelta


@pytest.fixture(autouse=True)
def auth_audit_mock():
    with patch("app.routes_auth.record_audit_event") as record:
        yield record


def _make_app() -> Flask:
    Config.KARTA_OFFICE_USERS = (
        '[{"username":"admin","password":"pw","role":"admin"},'
        '{"username":"office","password":"pw","role":"office"},'
        '{"username":"viewer","password":"pw","role":"viewer"}]'
    )
    Config.KARTA_OFFICE_LOGIN_USER = ""
    Config.KARTA_OFFICE_LOGIN_PASSWORD = ""

    app = Flask(__name__)
    app.secret_key = "test-secret"
    register_access_context(app)
    register_login_guard(app)
    app.register_blueprint(auth_bp)
    app.add_url_rule("/api/employees/list", "employees", lambda: {"ok": True})
    app.add_url_rule("/api/store/save", "store_save", lambda: {"ok": True}, methods=["POST"])
    app.add_url_rule("/api/sync-log/runs", "sync_log_runs", lambda: {"ok": True})
    app.add_url_rule("/ui/sync", "ui_sync", lambda: "sync")
    app.add_url_rule("/ui/sync-log", "ui_sync_log", lambda: "sync-log")
    app.add_url_rule("/ui/stores/notify", "ui_store_notify", lambda: "notify")
    return app


def test_viewer_can_read_but_cannot_write():
    client = _make_app().test_client()

    assert client.get("/api/employees/list").status_code == 401
    login = client.post("/api/auth/login", json={"username": "viewer", "password": "pw"})

    assert login.status_code == 200
    assert login.json["role"] == "viewer"
    assert client.get("/api/employees/list").status_code == 200
    assert client.post("/api/store/save").status_code == 403


def test_login_and_logout_are_audited(auth_audit_mock):
    client = _make_app().test_client()

    login = client.post("/api/auth/login", json={"username": "viewer", "password": "pw"})
    logout = client.post("/api/auth/logout")

    assert login.status_code == 200
    assert logout.status_code == 200
    assert auth_audit_mock.call_count == 2
    assert auth_audit_mock.call_args_list[0].kwargs["action"] == "auth.login_success"
    assert auth_audit_mock.call_args_list[0].kwargs["entity_id"] == "viewer"
    assert auth_audit_mock.call_args_list[0].kwargs["success"] is True
    assert auth_audit_mock.call_args_list[1].kwargs["action"] == "auth.logout"
    assert auth_audit_mock.call_args_list[1].kwargs["entity_id"] == "viewer"


def test_failed_login_is_audited(auth_audit_mock):
    client = _make_app().test_client()

    response = client.post("/api/auth/login", json={"username": "viewer", "password": "bad"})

    assert response.status_code == 401
    auth_audit_mock.assert_called_once()
    assert auth_audit_mock.call_args.kwargs["action"] == "auth.login_failed"
    assert auth_audit_mock.call_args.kwargs["entity_id"] == "viewer"
    assert auth_audit_mock.call_args.kwargs["success"] is False
    assert auth_audit_mock.call_args.kwargs["http_status"] == 401
    assert auth_audit_mock.call_args.kwargs["details"]["reason"] == "invalid_credentials"


def test_restricted_ui_redirects_to_home():
    client = _make_app().test_client()

    client.post("/api/auth/login", json={"username": "viewer", "password": "pw"})
    response = client.get("/ui/sync")

    assert response.status_code == 302
    assert response.location == "/ui/"


def test_office_user_cannot_access_global_sync():
    client = _make_app().test_client()

    client.post("/api/auth/login", json={"username": "office", "password": "pw"})
    response = client.get("/ui/sync")

    assert response.status_code == 302
    assert response.location == "/ui/"


def test_office_manager_menu_hides_admin_only_items_even_with_permissions():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    register_access_context(app)
    app.add_url_rule(
        "/ui/",
        "home",
        lambda: render_template_string("""
        {% for item in office_nav_items %}
          {% if office_nav_item_allowed(item) %}{{ item.label }} {% endif %}
        {% endfor %}
        """),
    )
    client = app.test_client()

    with client.session_transaction() as session:
        session[SESSION_LOGGED_IN] = True
        session[SESSION_USER] = "makis"
        session[SESSION_ROLE] = "office_manager"
        session[SESSION_SUPER_ADMIN] = False
        session[SESSION_PERMISSIONS] = ["sync.view", "notifications.view", "logs.view", "dashboard.view"]

    html = client.get("/ui/").get_data(as_text=True)

    assert "Συγχρονισμός" not in html
    assert "Ειδοποιήσεις" not in html
    assert "Καταγραφές" not in html


def test_role_aliases_do_not_fallback_to_super_admin():
    assert normalize_role("office manager") == "office_manager"
    assert normalize_role("office-manager") == "office_manager"
    assert normalize_role("backoffice") == "backoffice_admin"
    assert normalize_role("not-a-real-role") == "viewer"


def test_non_admin_sync_permissions_are_limited_to_work_card_refresh():
    office_permissions = permissions_for_role("office_manager")

    assert "work_card.sync_refresh" in office_permissions
    assert "schedule.sync" not in office_permissions
    assert "work_log.sync" not in office_permissions
    assert "monthly_status.sync" not in office_permissions
    assert "missing_cards.sync_refresh" not in office_permissions
    assert "sync.view" not in office_permissions


def test_work_card_sync_uses_separate_permission():
    assert permission_for_path("/api/work-log/work-card-sync", "POST") == "work_card.sync_refresh"
    assert permission_for_path("/api/work-log/sync", "POST") == "work_log.sync"


def test_non_admin_work_card_sync_only_allows_today():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    register_access_context(app)
    register_login_guard(app)
    app.register_blueprint(work_log_bp)
    client = app.test_client()
    today = datetime.now(tz_athens()).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    ctx = {
        "id": 7,
        "name": "Store",
        "employer_afm": "123456789",
        "branch_aa": "0",
    }

    with client.session_transaction() as session:
        session[SESSION_LOGGED_IN] = True
        session[SESSION_USER] = "makis"
        session[SESSION_ROLE] = "office_manager"
        session[SESSION_SUPER_ADMIN] = False
        session[SESSION_PERMISSIONS] = sorted(permissions_for_role("office_manager"))

    with (
        patch("app.routes_work_log.resolve_active_store", return_value=ctx),
        patch(
            "app.routes_work_log.start_async_portal_sync",
            return_value={"async": True, "job_id": "test-job"},
        ) as sync,
    ):
        rejected = client.post("/api/work-log/work-card-sync", json={"date": yesterday})
        accepted = client.post("/api/work-log/work-card-sync", json={"date": today.isoformat()})

    assert rejected.status_code == 403
    assert "μόνο για σήμερα" in rejected.json["error"]
    assert accepted.status_code == 200
    sync.assert_called_once()


def test_notifications_and_logs_are_admin_only():
    client = _make_app().test_client()

    client.post("/api/auth/login", json={"username": "viewer", "password": "pw"})

    assert client.get("/ui/sync-log").status_code == 302
    assert client.get("/ui/sync-log").location == "/ui/"
    assert client.get("/ui/stores/notify").status_code == 302
    assert client.get("/ui/stores/notify").location == "/ui/"
    assert client.get("/api/sync-log/runs").status_code == 403


def test_admin_can_write():
    client = _make_app().test_client()

    login = client.post("/api/auth/login", json={"username": "admin", "password": "pw"})

    assert login.status_code == 200
    assert login.json["role"] == "admin"
    assert client.post("/api/store/save").status_code == 200
    assert client.get("/ui/sync-log").status_code == 200
    assert client.get("/ui/stores/notify").status_code == 200
    assert client.get("/api/sync-log/runs").status_code == 200


def test_db_login_enqueues_sync_for_user_stores():
    client = _make_app().test_client()
    db_user = {
        "id": 42,
        "username": "office-user",
        "role": "office",
        "permissions": ["dashboard.view"],
        "is_super_admin": False,
        "store_ids": [7, 9],
    }

    with (
        patch("app.repo_users.authenticate_user", return_value=db_user),
        patch("app.scheduled_sync.enqueue_sync_allowed_stores_after_login") as enqueue,
    ):
        login = client.post(
            "/api/auth/login",
            json={"username": "office-user", "password": "pw"},
        )

    assert login.status_code == 200
    enqueue.assert_called_once_with(user_id=42, store_ids=[7, 9])


def test_db_super_admin_login_enqueues_sync_for_all_stores():
    client = _make_app().test_client()
    db_user = {
        "id": 1,
        "username": "admin",
        "role": "super_admin",
        "permissions": ["*"],
        "is_super_admin": True,
        "store_ids": [],
    }

    with (
        patch("app.repo_users.authenticate_user", return_value=db_user),
        patch("app.scheduled_sync.enqueue_sync_allowed_stores_after_login") as enqueue,
    ):
        login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "pw"},
        )

    assert login.status_code == 200
    enqueue.assert_called_once_with(user_id=1, store_ids=None)


def test_user_save_requires_store_scope_for_non_super_admin():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(users_bp)
    client = app.test_client()

    with (
        patch("app.repo_users.tables_available", return_value=True),
        patch("app.repo_users.create_user") as create_user,
    ):
        response = client.post(
            "/api/users",
            json={
                "username": "office-user",
                "password": "pw",
                "role": "office",
                "store_ids": [],
            },
        )

    assert response.status_code == 400
    assert "κατάστημα" in response.json["error"]
    create_user.assert_not_called()


def test_user_create_sends_email_verification():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(users_bp)
    client = app.test_client()
    user = {
        "id": 9,
        "username": "new-user",
        "email": "new@example.gr",
        "full_name": "New User",
        "role": "office",
        "is_active": True,
        "permissions": [],
        "store_ids": [7],
    }

    with (
        patch("app.repo_users.tables_available", return_value=True),
        patch("app.repo_users.create_user", return_value=9),
        patch("app.repo_users.get_user", return_value=user),
        patch("app.repo_users.create_email_verification_token", return_value="tok") as make_token,
        patch("app.routes_users.send_verification_email") as send_email,
    ):
        response = client.post(
            "/api/users",
            json={
                "username": "new-user",
                "password": "pw",
                "email": "new@example.gr",
                "role": "office",
                "store_ids": [7],
            },
        )

    assert response.status_code == 200
    assert response.json["success"] is True
    make_token.assert_called_once_with(9)
    send_email.assert_called_once()
    assert send_email.call_args.kwargs["email"] == "new@example.gr"
    assert send_email.call_args.kwargs["token"] == "tok"


def test_user_email_verify_endpoint_consumes_token():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.register_blueprint(users_bp)
    client = app.test_client()

    with patch(
        "app.repo_users.verify_email_token",
        return_value={"id": 9, "username": "new-user", "email": "new@example.gr"},
    ) as verify:
        response = client.get("/api/users/verify-email?t=tok")

    assert response.status_code == 200
    assert response.json["success"] is True
    verify.assert_called_once_with("tok")
