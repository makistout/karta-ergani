from flask import Flask

from app.routes_assistant import assistant_bp
from app.telegram_assistant_health import assistant_health, check_source, crash_is_newer


def test_current_assistant_source_compiles():
    result = check_source()
    assert result["ok"] is True
    assert result["error"] is None


def test_broken_source_is_detected(tmp_path):
    bad = tmp_path / "telegram_assistant_service.py"
    bad.write_text("if True:\nbreak\n", encoding="utf-8")
    result = check_source(bad)
    assert result["ok"] is False
    assert "IndentationError" in str(result["error"])


def test_old_crash_before_success_is_not_warning():
    assert crash_is_newer(
        {"received_at": "2026-09-23T20:30:51+03:00"},
        {"created_at": "2026-09-23T22:04:06+03:00"},
    ) is False
    assert crash_is_newer(
        {"received_at": "2026-09-23T22:10:00+03:00"},
        {"created_at": "2026-09-23T22:04:06+03:00"},
    ) is True


def test_health_payload_has_status_for_current_file(monkeypatch):
    monkeypatch.setattr("app.telegram_assistant_health.recent_inbound_crash", lambda **kwargs: None)
    monkeypatch.setattr("app.telegram_assistant_health.last_successful_task", lambda: None)
    health = assistant_health(use_cache=False)
    assert health["status"] == "ok"
    assert health["ok"] is True
    assert health["label"] == "AI Agent"


def test_health_api_forbidden_for_non_super_admin(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(assistant_bp)
    monkeypatch.setattr("app.routes_assistant.is_super_admin", lambda: False)
    with app.test_client() as client:
        response = client.get("/api/assistant/health")
    assert response.status_code == 403


def test_health_api_ok_for_super_admin(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(assistant_bp)
    monkeypatch.setattr("app.routes_assistant.is_super_admin", lambda: True)
    monkeypatch.setattr(
        "app.telegram_assistant_health.assistant_health",
        lambda: {"ok": True, "status": "ok", "label": "AI Agent", "detail": "ok"},
    )
    with app.test_client() as client:
        response = client.get("/api/assistant/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
