from flask import Flask
from unittest.mock import patch

from app.office_auth import register_login_guard
from app.routes_auth import auth_bp
from config import Config


def _make_app() -> Flask:
    Config.KARTA_OFFICE_USERS = (
        '[{"username":"admin","password":"pw","role":"admin"},'
        '{"username":"viewer","password":"pw","role":"viewer"}]'
    )
    Config.KARTA_OFFICE_LOGIN_USER = ""
    Config.KARTA_OFFICE_LOGIN_PASSWORD = ""

    app = Flask(__name__)
    app.secret_key = "test-secret"
    register_login_guard(app)
    app.register_blueprint(auth_bp)
    app.add_url_rule("/api/employees/list", "employees", lambda: {"ok": True})
    app.add_url_rule("/api/store/save", "store_save", lambda: {"ok": True}, methods=["POST"])
    app.add_url_rule("/ui/sync", "ui_sync", lambda: "sync")
    return app


def test_viewer_can_read_but_cannot_write():
    client = _make_app().test_client()

    assert client.get("/api/employees/list").status_code == 401
    login = client.post("/api/auth/login", json={"username": "viewer", "password": "pw"})

    assert login.status_code == 200
    assert login.json["role"] == "viewer"
    assert client.get("/api/employees/list").status_code == 200
    assert client.post("/api/store/save").status_code == 403


def test_restricted_ui_redirects_to_home():
    client = _make_app().test_client()

    client.post("/api/auth/login", json={"username": "viewer", "password": "pw"})
    response = client.get("/ui/sync")

    assert response.status_code == 302
    assert response.location == "/ui/"


def test_admin_can_write():
    client = _make_app().test_client()

    login = client.post("/api/auth/login", json={"username": "admin", "password": "pw"})

    assert login.status_code == 200
    assert login.json["role"] == "admin"
    assert client.post("/api/store/save").status_code == 200


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
