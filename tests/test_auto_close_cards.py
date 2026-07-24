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
    assert "Υποβολές εξόδου: 3/4" in text
    assert "Αποτυχίες: 1" in text
