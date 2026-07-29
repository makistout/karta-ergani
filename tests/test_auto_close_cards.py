from __future__ import annotations

from datetime import datetime

import pytest

import app.auto_close_cards as auto_close_cards
from app.auto_close_cards import should_run_auto_close_prev_day
from app.work_card_payload import tz_athens


@pytest.fixture(autouse=True)
def _disable_punch_time_jitter(monkeypatch):
    """Σταθερές ώρες στα unit tests — χωρίς ±5′ jitter."""
    monkeypatch.setattr(
        auto_close_cards,
        "apply_punch_time_jitter",
        lambda total_minutes, *, rng=None: int(total_minutes),
    )


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


def test_auto_close_evening_closes_current_day_without_overnight():
    cfg = {
        "auto_close_prev_day_enabled": True,
        "auto_close_prev_day_time": "23:00",
        "auto_close_prev_day_last_run_date": None,
    }

    ok, work_date, reason = should_run_auto_close_prev_day(
        cfg,
        now=datetime(2026, 7, 1, 23, 5, tzinfo=tz_athens()),
    )

    assert ok is True
    assert work_date == "2026-07-01"
    assert reason == "έτοιμο"
    assert auto_close_cards.auto_close_allows_overnight_star(cfg) is False


def test_auto_close_does_not_run_hours_after_configured_time():
    """02:00 στις 20:45 δεν πρέπει να κλείνει — μόνο μέσα στο παράθυρο μετά την ώρα."""
    cfg = {
        "auto_close_prev_day_enabled": True,
        "auto_close_prev_day_time": "02:00",
        "auto_close_prev_day_last_run_date": None,
    }

    ok, work_date, reason = should_run_auto_close_prev_day(
        cfg,
        now=datetime(2026, 7, 28, 20, 45, tzinfo=tz_athens()),
    )

    assert ok is False
    assert work_date == "2026-07-27"
    assert "παραθύρου" in reason


def test_auto_close_runs_inside_window_after_configured_time():
    cfg = {
        "auto_close_prev_day_enabled": True,
        "auto_close_prev_day_time": "02:00",
        "auto_close_prev_day_last_run_date": None,
    }

    ok, work_date, reason = should_run_auto_close_prev_day(
        cfg,
        now=datetime(2026, 7, 28, 2, 15, tzinfo=tz_athens()),
    )

    assert ok is True
    assert work_date == "2026-07-27"
    assert reason == "έτοιμο"


def test_auto_close_evening_waits_before_run_time():
    cfg = {
        "auto_close_prev_day_enabled": True,
        "auto_close_prev_day_time": "23:00",
        "auto_close_prev_day_last_run_date": None,
    }

    ok, work_date, reason = should_run_auto_close_prev_day(
        cfg,
        now=datetime(2026, 7, 1, 22, 30, tzinfo=tz_athens()),
    )

    assert ok is False
    assert work_date == "2026-07-01"
    assert "23:00" in reason


def test_build_previous_day_close_plan_uses_schedule_duration(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 1,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "17:00",
            "hour_to": "",
            "portal_hour_from": "17:00",
            "portal_hour_to": "",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "17:00", "hour_to": "01:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert skipped == []
    assert plan[0]["retro_time"] == "01:00"
    assert plan[0]["reference_date"] == "2026-06-30"
    assert plan[0]["event_date_iso"] == "2026-07-01"
    assert plan[0]["duration_source"] == "schedule"


def test_build_close_plan_same_day_mode_skips_overnight_star(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 1,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-07-01",
            "hour_from": "17:00",
            "hour_to": "",
            "portal_hour_from": "17:00",
            "portal_hour_to": "",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "17:00", "hour_to": "01:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(
        rows,
        allow_overnight_star=False,
    )

    assert skipped == []
    assert plan[0]["retro_time"] == "01:00"
    assert plan[0]["reference_date"] == "2026-07-01"
    assert plan[0]["event_date_iso"] == "2026-07-01"


def test_build_previous_day_close_plan_uses_eight_hours_without_schedule(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 2,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "10:30",
            "hour_to": "",
            "portal_hour_from": "10:30",
            "portal_hour_to": "",
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


def test_build_previous_day_close_plan_skips_card_fallback_without_portal_entry(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": None,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "17:00",
            "hour_to": "",
            "portal_hour_from": "",
            "portal_hour_to": "",
            "from_card_event_fallback": True,
            "source_aa": "card_event_fallback",
            "hour_from_source": "card_event_fallback",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "17:00", "hour_to": "01:00"}],
        },
        {
            "id": 3,
            "employee_afm": "987654321",
            "eponymo": "REAL",
            "onoma": "PORTAL",
            "work_date_iso": "2026-06-30",
            "hour_from": "09:00",
            "hour_to": "",
            "portal_hour_from": "09:00",
            "portal_hour_to": "",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "09:00", "hour_to": "17:00"}],
        },
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert len(plan) == 1
    assert plan[0]["employee_afm"] == "987654321"
    assert plan[0]["hour_from"] == "09:00"
    assert any(s["employee_afm"] == "123456789" and "πραγματική" in s["reason"] for s in skipped)


def test_build_previous_day_close_plan_ignores_card_enriched_hour_from(monkeypatch):
    """Αν το portal δεν έχει Από, δεν κλείνουμε ακόμα κι αν η κάρτα γέμισε hour_from."""
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 4,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "17:00",
            "hour_to": "",
            "portal_hour_from": "",
            "portal_hour_to": "",
            "hour_from_source": "card_event_fallback",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "17:00", "hour_to": "01:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert plan == []
    assert skipped and "πραγματική" in skipped[0]["reason"]


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
    assert "Υποβολές εισόδου/εξόδου: 3/4" in text
    assert "Αποτυχίες: 1" in text


def test_build_close_plan_fills_missing_entry_same_day(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 10,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "",
            "hour_to": "16:00",
            "portal_hour_from": "",
            "portal_hour_to": "16:00",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "08:00", "hour_to": "16:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert skipped == []
    assert plan[0]["event"] == "check_in"
    assert plan[0]["retro_time"] == "08:00"
    assert plan[0]["reference_date"] == "2026-06-30"
    assert plan[0]["event_date_iso"] == "2026-06-30"


def test_build_close_plan_fills_missing_entry_overnight_orphan(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 11,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "",
            "hour_to": "01:00",
            "portal_hour_from": "",
            "portal_hour_to": "01:00",
            "overnight_exit_orphan": True,
            "employee_active": True,
            "schedule_slots": [{"hour_from": "17:00", "hour_to": "01:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert skipped == []
    assert plan[0]["event"] == "check_in"
    assert plan[0]["retro_time"] == "17:00"
    assert plan[0]["reference_date"] == "2026-06-30"
    assert plan[0]["event_date_iso"] == "2026-06-30"


def test_build_close_plan_skips_early_exit_only_on_same_calendar_day(monkeypatch):
    """Έξοδος 01:00 χωρίς είσοδο στην ίδια ημερολογιακή μέρα ανήκει στην προηγούμενη — skip εδώ."""
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 12,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-07-01",
            "hour_from": "",
            "hour_to": "01:00",
            "portal_hour_from": "",
            "portal_hour_to": "01:00",
            "overnight_exit_orphan": False,
            "employee_active": True,
            "schedule_slots": [{"hour_from": "17:00", "hour_to": "01:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert plan == []
    assert skipped == []


def test_build_close_plan_uses_eight_hours_for_missing_entry(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 13,
            "employee_afm": "123456789",
            "eponymo": "TEST",
            "onoma": "USER",
            "work_date_iso": "2026-06-30",
            "hour_from": "",
            "hour_to": "18:30",
            "portal_hour_from": "",
            "portal_hour_to": "18:30",
            "employee_active": True,
            "schedule_slots": [],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(rows)

    assert skipped == []
    assert plan[0]["event"] == "check_in"
    assert plan[0]["retro_time"] == "10:30"
    assert plan[0]["duration_source"] == "rest_8h"


def test_auto_close_queue_delay_seconds_uses_config_range(monkeypatch):
    monkeypatch.setattr(
        auto_close_cards.Config,
        "KARTA_AUTO_CLOSE_QUEUE_MIN_DELAY_SECONDS",
        120,
    )
    monkeypatch.setattr(
        auto_close_cards.Config,
        "KARTA_AUTO_CLOSE_QUEUE_MAX_DELAY_SECONDS",
        180,
    )
    monkeypatch.setattr(auto_close_cards.random, "randint", lambda low, high: 133)

    assert auto_close_cards._auto_close_queue_delay_seconds() == 133
