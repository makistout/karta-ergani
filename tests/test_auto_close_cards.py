from __future__ import annotations

from datetime import datetime

import app.auto_close_cards as auto_close_cards
from app.auto_close_cards import should_run_auto_close_prev_day
from app.work_card_payload import tz_athens


def test_auto_close_prev_day_waits_until_configured_time():
    cfg = {
        "auto_close_prev_day_enabled": True,
        "auto_close_prev_day_time": "02:15",
        "auto_close_prev_day_last_run_date": None,
    }

    ok, work_date, reason = should_run_auto_close_prev_day(
        cfg,
        now=datetime(2026, 7, 1, 1, 30, tzinfo=tz_athens()),
    )

    assert ok is False
    assert work_date == "2026-06-30"
    assert "02:15" in reason


def test_auto_close_prev_day_skips_already_processed_previous_day():
    cfg = {
        "auto_close_prev_day_enabled": True,
        "auto_close_prev_day_time": "00:30",
        "auto_close_prev_day_last_run_date": "2026-06-30",
    }

    ok, work_date, reason = should_run_auto_close_prev_day(
        cfg,
        now=datetime(2026, 7, 1, 3, 0, tzinfo=tz_athens()),
    )

    assert ok is False
    assert work_date == "2026-06-30"
    assert "ήδη" in reason


def test_build_previous_day_close_plan_uses_schedule_duration(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "17:00",
            "hour_to": "",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "17:00", "hour_to": "01:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert skipped == []
    assert plan[0]["retro_time"] == "01:00"
    assert plan[0]["reference_date"] == "2026-07-01"
    assert plan[0]["duration_source"] == "schedule"


def test_build_previous_day_close_plan_uses_eight_hours_without_schedule(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "10:30",
            "hour_to": "",
            "employee_active": True,
            "schedule_label": "Ρεπό",
            "schedule_slots": [],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert skipped == []
    assert plan[0]["retro_time"] == "18:30"
    assert plan[0]["reference_date"] == "2026-06-30"
    assert plan[0]["duration_source"] == "rest_8h"


def test_format_auto_close_notification_text():
    text = auto_close_cards.format_auto_close_notification_text(
        store_name="STORE",
        work_date_iso="2026-06-30",
        submitted=3,
        failed=1,
        skipped=2,
        plan_count=4,
    )

    assert "STORE" in text
    assert "30/06/2026" in text
    assert "Υποβολές εξόδου: 3/4" in text
    assert "Αποτυχίες: 1" in text
