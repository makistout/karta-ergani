from __future__ import annotations

from unittest.mock import patch

from flask import Flask

from app.routes_auth import auth_bp
from app.user_password_reset import RESET_TOKEN_TTL_HOURS, build_password_reset_email


def test_password_reset_email_content():
    text, html_body = build_password_reset_email(
        username="makis",
        full_name="Makis Test",
        url="https://erganios.gr/ui/reset-password?t=abc",
    )
    assert "Makis Test" in text
    assert "makis" in text
    assert f"{RESET_TOKEN_TTL_HOURS} ώρες" in text
    assert "Ορισμός νέου κωδικού" in html_body
    assert "reset-password?t=abc" in html_body


def test_forgot_password_antienumeration():
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(auth_bp)
    client = app.test_client()

    with (
        patch("app.routes_auth.office_login_enabled", return_value=True),
        patch("app.repo_users.password_reset_available", return_value=True),
        patch("app.repo_users.find_active_user_for_password_reset", return_value=None),
    ):
        res = client.post("/api/auth/forgot-password", json={"identity": "nobody"})
    assert res.status_code == 200
    assert res.json["success"] is True
    assert "email" in res.json["message"].lower()


def test_forgot_password_sends_email():
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(auth_bp)
    client = app.test_client()
    user = {
        "id": 2,
        "username": "makis",
        "email": "makis@example.gr",
        "full_name": "Makis",
        "is_active": True,
    }

    with (
        patch("app.routes_auth.office_login_enabled", return_value=True),
        patch("app.repo_users.password_reset_available", return_value=True),
        patch("app.repo_users.find_active_user_for_password_reset", return_value=user),
        patch("app.repo_users.create_password_reset_token", return_value="tok123") as make_token,
        patch("app.routes_auth._record_auth_event"),
        patch("app.user_password_reset.send_password_reset_email") as send_email,
    ):
        res = client.post("/api/auth/forgot-password", json={"username": "makis"})

    assert res.status_code == 200
    assert res.json["success"] is True
    make_token.assert_called_once_with(2)
    send_email.assert_called_once()
    assert send_email.call_args.kwargs["email"] == "makis@example.gr"
    assert send_email.call_args.kwargs["token"] == "tok123"


def test_reset_password_endpoint_validates_confirm():
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(auth_bp)
    client = app.test_client()

    with patch("app.routes_auth.office_login_enabled", return_value=True):
        res = client.post(
            "/api/auth/reset-password",
            json={
                "token": "abc",
                "new_password": "newpass12",
                "confirm_password": "other",
            },
        )
    assert res.status_code == 400
    assert "ταιριάζει" in res.json["error"]


def test_reset_password_endpoint_success():
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(auth_bp)
    client = app.test_client()

    with (
        patch("app.routes_auth.office_login_enabled", return_value=True),
        patch("app.repo_users.reset_password_with_token", return_value=None) as reset,
        patch("app.routes_auth._record_auth_event"),
    ):
        res = client.post(
            "/api/auth/reset-password",
            json={
                "token": "abc",
                "new_password": "newpass12",
                "confirm_password": "newpass12",
            },
        )
    assert res.status_code == 200
    assert res.json["success"] is True
    reset.assert_called_once_with("abc", "newpass12")
