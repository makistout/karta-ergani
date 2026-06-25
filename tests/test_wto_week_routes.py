from flask import Flask, session

from app import routes_wto_week


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 400
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self):
        self.tokens = []

    def submissions_list(self, bearer):
        self.tokens.append(bearer)
        if bearer == "old-token":
            return FakeResponse(401, {"message": "expired"})
        return FakeResponse(200, [{"code": "WTOWeek"}])


def test_wto_week_availability_refreshes_expired_session_token(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    client = FakeClient()

    def fake_ensure_ergani_bearer(ctx):
        token = session.get("ergani_bearer")
        if token:
            return token
        session["ergani_bearer"] = "new-token"
        return "new-token"

    monkeypatch.setattr(routes_wto_week, "ensure_ergani_bearer", fake_ensure_ergani_bearer)

    with app.test_request_context("/"):
        session["ergani_bearer"] = "old-token"

        bearer, available, status, parsed = routes_wto_week._availability_with_token_refresh(
            {"id": 1},
            client,
        )

        assert bearer == "new-token"
        assert available is True
        assert status == 200
        assert parsed == [{"code": "WTOWeek"}]
        assert client.tokens == ["old-token", "new-token"]
