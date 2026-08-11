from datetime import datetime
from zoneinfo import ZoneInfo

from app import scheduled_sync


def _settings(monkeypatch):
    monkeypatch.setattr(scheduled_sync.Config, "KARTA_SCHEDULED_APOLOGISTIC_ENABLED", True)
    monkeypatch.setattr(scheduled_sync.Config, "KARTA_SCHEDULED_APOLOGISTIC_WEEKDAY", 0)
    monkeypatch.setattr(scheduled_sync.Config, "KARTA_SCHEDULED_APOLOGISTIC_TIME", "03:00")


def test_waits_until_monday_0300(monkeypatch):
    _settings(monkeypatch)
    now = datetime(2026, 8, 10, 2, 59, tzinfo=ZoneInfo("Europe/Athens"))
    assert scheduled_sync.should_run_apologistic_snapshot({"id": 1}, now=now)[0] is False


def test_runs_for_missing_previous_week(monkeypatch):
    _settings(monkeypatch)
    monkeypatch.setattr("app.repo_apologistic.tables_available", lambda: True)
    monkeypatch.setattr("app.repo_apologistic.get_run", lambda *_: None)
    now = datetime(2026, 8, 10, 3, 0, tzinfo=ZoneInfo("Europe/Athens"))
    assert scheduled_sync.should_run_apologistic_snapshot({"id": 1}, now=now) == (True, "έτοιμο")


def test_does_not_overwrite_existing_draft(monkeypatch):
    _settings(monkeypatch)
    monkeypatch.setattr("app.repo_apologistic.tables_available", lambda: True)
    monkeypatch.setattr("app.repo_apologistic.get_run", lambda *_: {"status": "draft"})
    now = datetime(2026, 8, 10, 3, 15, tzinfo=ZoneInfo("Europe/Athens"))
    assert scheduled_sync.should_run_apologistic_snapshot({"id": 1}, now=now)[0] is False
