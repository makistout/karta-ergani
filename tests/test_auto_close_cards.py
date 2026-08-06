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


def test_build_close_plan_uses_next_day_open_entry_as_exit(monkeypatch):
    """Αν υπάρχει ανοιχτή είσοδος στην επόμενη μέρα < 03:00, η έξοδος = εκείνη η ώρα με *."""
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 20,
            "employee_afm": "202331454",
            "eponymo": "LUVA",
            "onoma": "CHRISTIAN JAY",
            "work_date_iso": "2026-07-28",
            "hour_from": "15:56",
            "hour_to": "",
            "portal_hour_from": "15:56",
            "portal_hour_to": "",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "16:00", "hour_to": "00:00"}],
        }
    ]
    next_day_open_entries = {"202331454": 59}  # 00:59

    plan, skipped = auto_close_cards._build_previous_day_close_plan(
        rows,
        allow_overnight_star=True,
        next_day_open_entries=next_day_open_entries,
    )

    assert skipped == []
    assert len(plan) == 1
    assert plan[0]["event"] == "check_out"
    assert plan[0]["retro_time"] == "00:59"
    assert plan[0]["reference_date"] == "2026-07-28"
    assert plan[0]["event_date_iso"] == "2026-07-29"


def test_build_close_plan_normal_exit_when_no_next_day_entry(monkeypatch):
    """Χωρίς ανοιχτή είσοδο στην επόμενη, η κανονική λογική (entry + duration)."""
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "id": 21,
            "employee_afm": "202331454",
            "eponymo": "LUVA",
            "onoma": "CHRISTIAN JAY",
            "work_date_iso": "2026-07-28",
            "hour_from": "15:56",
            "hour_to": "",
            "portal_hour_from": "15:56",
            "portal_hour_to": "",
            "employee_active": True,
            "schedule_slots": [{"hour_from": "16:00", "hour_to": "00:00"}],
        }
    ]

    plan, skipped = auto_close_cards._build_previous_day_close_plan(
        rows,
        allow_overnight_star=True,
        next_day_open_entries={},
    )

    assert plan[0]["retro_time"] == "23:56"
    assert plan[0]["reference_date"] == "2026-07-28"
    assert plan[0]["event_date_iso"] == "2026-07-28"


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

def test_normalize_optional_auto_close_time():
    assert auto_close_cards.normalize_optional_auto_close_time("") is None
    assert auto_close_cards.normalize_optional_auto_close_time(None) is None
    assert auto_close_cards.normalize_optional_auto_close_time("23.00") == "23:00"
    assert auto_close_cards.normalize_optional_auto_close_time("23:00") == "23:00"
    assert auto_close_cards.normalize_optional_auto_close_time("25:00") is None


def test_fixed_exit_window_assigns_random_times_in_half_hour(monkeypatch):
    """Βάρδιες που θα έκλειναν μετά τις 23:00 → τυχαία στο μισάωρο."""
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    import random

    rows = []
    for i, afm in enumerate(["111111111", "222222222", "333333333", "444444444", "555555555"]):
        rows.append({
            "employee_afm": afm,
            "eponymo": f"E{i}",
            "onoma": "T",
            "work_date_iso": "2026-08-03",
            "portal_hour_from": "16:00",
            "portal_hour_to": "",
            "hour_from": "16:00",
            "hour_to": "",
            "employee_active": True,
            "schedule": {"hour_from": "16:00", "hour_to": "00:00"},
        })

    rng = random.Random(42)
    plan, skipped = auto_close_cards._build_previous_day_close_plan(
        rows,
        allow_overnight_star=False,
        fixed_exit_hm="23:00",
        rng=rng,
    )
    assert skipped == []
    assert len(plan) == 5
    times = sorted(p["retro_time"] for p in plan)
    assert len(set(times)) == 5
    for t in times:
        hh, mm = map(int, t.split(":"))
        total = hh * 60 + mm
        assert 23 * 60 <= total < 23 * 60 + 30
    assert all(p["duration_source"] == "fixed_window" for p in plan)


def test_fixed_exit_keeps_earlier_schedule_exits(monkeypatch):
    """Αν η έξοδος βάσει ωραρίου είναι πριν την ώρα κλεισίματος, μένει η ώρα ωραρίου."""
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [
        {
            "employee_afm": "111111111",
            "eponymo": "EARLY",
            "onoma": "T",
            "work_date_iso": "2026-08-03",
            "portal_hour_from": "09:00",
            "portal_hour_to": "",
            "hour_from": "09:00",
            "hour_to": "",
            "employee_active": True,
            "schedule": {"hour_from": "09:00", "hour_to": "17:00"},
        },
        {
            "employee_afm": "222222222",
            "eponymo": "LATE",
            "onoma": "T",
            "work_date_iso": "2026-08-03",
            "portal_hour_from": "16:00",
            "portal_hour_to": "",
            "hour_from": "16:00",
            "hour_to": "",
            "employee_active": True,
            "schedule": {"hour_from": "16:00", "hour_to": "00:00"},
        },
    ]
    import random

    plan, skipped = auto_close_cards._build_previous_day_close_plan(
        rows,
        allow_overnight_star=False,
        fixed_exit_hm="23:00",
        rng=random.Random(1),
    )
    assert skipped == []
    by_afm = {p["employee_afm"]: p for p in plan}
    assert by_afm["111111111"]["retro_time"] == "17:00"
    assert by_afm["111111111"]["duration_source"] == "schedule"
    late = by_afm["222222222"]["retro_time"]
    hh, mm = map(int, late.split(":"))
    assert 23 * 60 <= hh * 60 + mm < 23 * 60 + 30
    assert by_afm["222222222"]["duration_source"] == "fixed_window"


def test_empty_fixed_exit_keeps_schedule_based_times(monkeypatch):
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *args: False)
    rows = [{
        "employee_afm": "111111111",
        "eponymo": "E",
        "onoma": "T",
        "work_date_iso": "2026-08-03",
        "portal_hour_from": "09:00",
        "portal_hour_to": "",
        "hour_from": "09:00",
        "hour_to": "",
        "employee_active": True,
        "schedule": {"hour_from": "09:00", "hour_to": "17:00"},
    }]
    plan, _ = auto_close_cards._build_previous_day_close_plan(
        rows, allow_overnight_star=False, fixed_exit_hm=""
    )
    assert len(plan) == 1
    assert plan[0]["retro_time"] == "17:00"
    assert plan[0]["duration_source"] == "schedule"


def test_auto_close_retries_without_aitiologia_when_ergani_forbids(monkeypatch):
    class FakeResp:
        def __init__(self, ok, status_code, payload):
            self.ok = ok
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self):
            self.calls = []

        def authenticate(self, *args, **kwargs):
            return FakeResp(True, 200, {"accessToken": "tok"})

        def document_submit(self, code, payload, bearer):
            self.calls.append(payload)
            details = (
                (payload.get("Cards") or {})
                .get("Card", [{}])[0]
                .get("Details", {})
                .get("CardDetails", [{}])
            )
            detail = details[0] if isinstance(details, list) and details else {}
            # First call with 001 → forbid; retry with null → OK
            if detail.get("f_aitiologia") == "001":
                return FakeResp(
                    False,
                    400,
                    {
                        "error": (
                            "Δεν πρέπει να δηλώνεται λόγος καθυστέρησης, όταν η ώρα "
                            "κίνησης είναι εντός του επιτρεπόμενου χρονικού ορίου."
                        )
                    },
                )
            return FakeResp(True, 200, [{"protocol": "P1"}])

    client = FakeClient()
    monkeypatch.setattr(auto_close_cards, "client_for_store", lambda cfg: client)
    monkeypatch.setattr(
        auto_close_cards,
        "api_login_credentials",
        lambda cfg: ("u", "p", "01"),
    )
    monkeypatch.setattr(auto_close_cards, "store_api_context", lambda cfg: {
        "employer_afm": "999999999",
        "branch_aa": "0",
    })
    monkeypatch.setattr(
        auto_close_cards,
        "_load_previous_day_rows",
        lambda *a, **k: (
            [{
                "employee_afm": "122643591",
                "eponymo": "TEST",
                "onoma": "USER",
                "work_date_iso": "2026-08-05",
                "portal_hour_from": "18:00",
                "portal_hour_to": "",
                "hour_from": "18:00",
                "hour_to": "",
                "employee_active": True,
                "schedule": {"hour_from": "18:00", "hour_to": "01:00"},
            }],
            {},
        ),
    )
    monkeypatch.setattr(auto_close_cards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(auto_close_cards, "has_entry_for_checkout", lambda **k: True)
    monkeypatch.setattr(auto_close_cards, "persist_wrk_card_submit", lambda *a, **k: None)
    monkeypatch.setattr(auto_close_cards, "record_audit_event", lambda **k: None)
    monkeypatch.setattr(
        auto_close_cards,
        "_send_auto_close_notification",
        lambda **k: {"sent": False},
    )
    monkeypatch.setattr(auto_close_cards, "_auto_close_queue_delay_seconds", lambda: 0)
    monkeypatch.setattr(
        auto_close_cards,
        "apply_punch_time_jitter",
        lambda *a, **k: a[0] if a else k.get("hm"),
    )

    result = auto_close_cards.run_auto_close_prev_day_for_store(
        {
            "id": 11,
            "name": "TEST",
            "auto_close_prev_day_time": "02:00",
            "auto_close_fixed_exit_time": None,
        },
        work_date_iso="2026-08-05",
    )
    assert result["submitted"] == 1
    assert result["failed"] == 0
    assert len(client.calls) == 2
    first = client.calls[0]["Cards"]["Card"][0]["Details"]["CardDetails"][0]
    second = client.calls[1]["Cards"]["Card"][0]["Details"]["CardDetails"][0]
    assert first.get("f_aitiologia") == "001"
    assert second.get("f_aitiologia") is None
