from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app import scheduled_sync
from config import Config


def test_should_run_employee_roster_before_time():
    cfg = {"id": 1}
    now = datetime(2026, 10, 2, 3, 50, tzinfo=ZoneInfo("Europe/Athens"))
    ok, reason = scheduled_sync.should_run_employee_roster_sync(cfg, now=now)
    assert ok is False
    assert "αναμονή" in reason


def test_should_run_employee_roster_respects_flag():
    cfg = {"id": 1}
    old = Config.KARTA_SCHEDULED_EMPLOYEE_ROSTER_ENABLED
    Config.KARTA_SCHEDULED_EMPLOYEE_ROSTER_ENABLED = False
    try:
        now = datetime(2026, 10, 2, 10, 0, tzinfo=ZoneInfo("Europe/Athens"))
        ok, reason = scheduled_sync.should_run_employee_roster_sync(cfg, now=now)
        assert ok is False
        assert "απενεργοποιημένο" in reason
    finally:
        Config.KARTA_SCHEDULED_EMPLOYEE_ROSTER_ENABLED = old
