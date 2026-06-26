from flask import Flask, session

from app import http_helpers


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {"accessToken": "new-token"}


class FakeErganiClient:
    calls = 0

    def __init__(self, base_url=None):
        self.base_url = base_url

    def authenticate(self, username, password, usertype):
        FakeErganiClient.calls += 1
        return FakeResponse()


def _app():
    app = Flask(__name__)
    app.secret_key = "test"
    return app


def test_ensure_ergani_bearer_ignores_token_from_other_store(monkeypatch):
    app = _app()
    FakeErganiClient.calls = 0
    monkeypatch.setattr("app.ergani_client.ErganiClient", FakeErganiClient)
    ctx = {
        "id": 4,
        "web_username": "user",
        "web_password": "pass",
        "usertype": "02",
        "ergani_env": "production",
        "api_base_url": "https://example.test/",
    }

    with app.test_request_context("/"):
        session["ergani_bearer"] = "old-token"
        session["ergani_bearer_store_id"] = "99"
        session["ergani_bearer_env"] = "production"

        token = http_helpers.ensure_ergani_bearer(ctx)

        assert token == "new-token"
        assert session["ergani_bearer_store_id"] == "4"
        assert FakeErganiClient.calls == 1


def test_ensure_ergani_bearer_reuses_token_for_same_store(monkeypatch):
    app = _app()
    FakeErganiClient.calls = 0
    monkeypatch.setattr("app.ergani_client.ErganiClient", FakeErganiClient)
    ctx = {
        "id": 4,
        "web_username": "user",
        "web_password": "pass",
        "usertype": "02",
        "ergani_env": "production",
    }

    with app.test_request_context("/"):
        session["ergani_bearer"] = "current-token"
        session["ergani_bearer_store_id"] = "4"
        session["ergani_bearer_env"] = "production"

        token = http_helpers.ensure_ergani_bearer(ctx)

        assert token == "current-token"
        assert FakeErganiClient.calls == 0
