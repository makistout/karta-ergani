# -*- coding: utf-8 -*-
from __future__ import annotations

import app.work_card_guards as guards


def test_has_entry_for_checkout_accepts_work_log_on_reference(monkeypatch):
    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(
        guards,
        "work_log_has_hour_from",
        lambda *a, **k: True,
    )
    assert guards.has_entry_for_checkout(
        employer_afm="123",
        branch_aa="1",
        employee_afm="171612465",
        reference_date_iso="2026-07-22",
        event_at="2026-07-23T00:51:00",
    )


def test_has_entry_for_checkout_rejects_without_entry(monkeypatch):
    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(guards, "work_log_has_hour_from", lambda *a, **k: False)
    assert not guards.has_entry_for_checkout(
        employer_afm="123",
        branch_aa="1",
        employee_afm="171612465",
        reference_date_iso="2026-07-23",
        event_at="2026-07-23T16:00:00",
    )


def test_has_entry_for_checkout_legacy_early_morning_uses_prev_day(monkeypatch):
    calls: list[str] = []

    def fake_card(emp, day, f_type):
        return False

    def fake_wl(employer, branch, emp, work_date):
        calls.append(work_date)
        # format_date_for_ergani of 2026-07-22
        return work_date in ("22/07/2026", "22/7/2026")

    monkeypatch.setattr(guards, "card_event_exists", fake_card)
    monkeypatch.setattr(guards, "work_log_has_hour_from", fake_wl)
    assert guards.has_entry_for_checkout(
        employer_afm="123",
        branch_aa="1",
        employee_afm="171612465",
        reference_date_iso="2026-07-23",
        event_at="2026-07-23T00:51:00",
    )


def test_has_entry_for_checkout_accepts_card_check_in(monkeypatch):
    monkeypatch.setattr(
        guards,
        "card_event_exists",
        lambda emp, day, f_type: f_type == "0" and day == "2026-07-22",
    )
    monkeypatch.setattr(guards, "work_log_has_hour_from", lambda *a, **k: False)
    assert guards.has_entry_for_checkout(
        employer_afm="123",
        branch_aa="1",
        employee_afm="171612465",
        reference_date_iso="2026-07-22",
        event_at="2026-07-22T23:00:00",
    )


def test_normalize_overnight_binds_calendar_exit_to_prev_work_day(monkeypatch):
    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(guards, "work_log_has_hour_from", lambda *a, **k: True)
    monkeypatch.setattr(
        guards,
        "work_log_has_open_entry",
        lambda *a, **k: True,
    )
    monkeypatch.setattr(guards, "work_log_open_hour_from", lambda *a, **k: "22:00")

    ref, event_at = guards.normalize_overnight_checkout_reference(
        employer_afm="123",
        branch_aa="1",
        employee_afm="171612465",
        reference_date_iso="2026-07-24",
        event_at="2026-07-24T00:54:00",
    )
    assert ref == "2026-07-23"
    assert event_at == "2026-07-24T00:54:00"


def test_normalize_overnight_advances_event_when_work_day_selected(monkeypatch):
    """Telegram/progenesterο: ημερομηνία = μέρα εργασίας, ώρα 00:54 → event επόμενη μέρα."""

    def open_entry(employer, branch, emp, work_date):
        return work_date in ("23/07/2026", "23/7/2026")

    def hour_from(employer, branch, emp, work_date):
        return work_date in ("23/07/2026", "23/7/2026")

    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(guards, "work_log_has_hour_from", hour_from)
    monkeypatch.setattr(guards, "work_log_has_open_entry", open_entry)
    monkeypatch.setattr(guards, "work_log_open_hour_from", lambda *a, **k: "22:00")

    ref, event_at = guards.normalize_overnight_checkout_reference(
        employer_afm="123",
        branch_aa="1",
        employee_afm="171612465",
        reference_date_iso="2026-07-23",
        event_at="2026-07-23T00:54:00",
    )
    assert ref == "2026-07-23"
    assert event_at == "2026-07-24T00:54:00"


def test_normalize_overnight_keeps_same_day_early_shift(monkeypatch):
    """Έναρξη 00:30 / έξοδος 02:00 ίδια μέρα — όχι overnight *."""

    def only_event_day(employer, branch, emp, work_date):
        return work_date in ("24/07/2026", "24/7/2026")

    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(guards, "work_log_has_hour_from", only_event_day)
    monkeypatch.setattr(guards, "work_log_has_open_entry", only_event_day)
    monkeypatch.setattr(guards, "work_log_open_hour_from", lambda *a, **k: "00:30")

    ref, event_at = guards.normalize_overnight_checkout_reference(
        employer_afm="123",
        branch_aa="1",
        employee_afm="171612465",
        reference_date_iso="2026-07-24",
        event_at="2026-07-24T02:00:00",
    )
    assert ref == "2026-07-24"
    assert event_at == "2026-07-24T02:00:00"


def test_new_card_punch_blocked_reason_rejects_closed_card_checkout(monkeypatch):
    monkeypatch.setattr(
        guards,
        "card_event_exists",
        lambda emp, day, f_type: f_type == "1",
    )
    monkeypatch.setattr(guards, "has_entry_for_checkout", lambda *a, **k: True)
    monkeypatch.setattr(guards, "latest_card_event_time_hm", lambda *a, **k: "18:30")
    monkeypatch.setattr(guards, "work_log_closed_hour_to", lambda *a, **k: None)
    monkeypatch.setattr(
        guards,
        "normalize_overnight_checkout_reference",
        lambda **k: (k["reference_date_iso"], k.get("event_at")),
    )
    reason = guards.new_card_punch_blocked_reason(
        intent="card_check_out_now",
        employer_afm="123456789",
        branch_aa="0",
        employee_afm="111222333",
        reference_date_iso="2026-08-18",
    )
    assert reason == "Δεν γίνεται κλείσιμο — υπάρχει ήδη δήλωση εξόδου στις 18:30."


def test_new_card_punch_blocked_reason_rejects_work_log_already_closed(monkeypatch):
    """Πραγματική με Από+Έως · χωρίς WRKCardSE out → απορρίπτεται το κλείσιμο."""
    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(guards, "work_log_closed_hour_to", lambda *a, **k: "20:00")
    monkeypatch.setattr(
        guards,
        "normalize_overnight_checkout_reference",
        lambda **k: (k["reference_date_iso"], k.get("event_at")),
    )
    reason = guards.new_card_punch_blocked_reason(
        intent="card_check_out_retro",
        employer_afm="123",
        branch_aa="0",
        employee_afm="111222333",
        reference_date_iso="2026-08-22",
        event_at="2026-08-22T23:00:00",
    )
    assert reason == (
        "Δεν γίνεται κλείσιμο — υπάρχει ήδη έξοδος στην πραγματική απασχόληση στις 20:00."
    )


def test_new_card_punch_blocked_reason_rejects_duplicate_check_in(monkeypatch):
    monkeypatch.setattr(
        guards,
        "card_event_exists",
        lambda emp, day, f_type: f_type == "0",
    )
    monkeypatch.setattr(guards, "work_log_has_open_entry", lambda *a, **k: False)
    monkeypatch.setattr(guards, "latest_card_event_time_hm", lambda *a, **k: "12:40")
    reason = guards.new_card_punch_blocked_reason(
        intent="card_check_in_now",
        employer_afm="123",
        branch_aa="0",
        employee_afm="111222333",
        reference_date_iso="2026-08-18",
    )
    assert reason == "Δεν γίνεται άνοιγμα — υπάρχει ήδη δήλωση εισόδου στις 12:40."


def test_new_card_punch_blocked_reason_rejects_check_in_when_work_log_open(monkeypatch):
    """Πραγματική ανοιχτή (χωρίς WRKCardSE) μετράει ως ήδη ανοιχτή κάρτα."""
    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(guards, "work_log_has_open_entry", lambda *a, **k: True)
    monkeypatch.setattr(guards, "work_log_open_hour_from", lambda *a, **k: "09:15")
    reason = guards.new_card_punch_blocked_reason(
        intent="card_check_in_retro",
        employer_afm="123",
        branch_aa="0",
        employee_afm="111222333",
        reference_date_iso="2026-08-20",
        event_at="2026-08-20T11:50:00",
    )
    assert (
        reason
        == "Δεν γίνεται άνοιγμα — υπάρχει ήδη ανοιχτή είσοδος στην πραγματική απασχόληση στις 09:15."
    )


def test_new_card_punch_blocked_reason_allows_open_checkout(monkeypatch):
    monkeypatch.setattr(guards, "card_event_exists", lambda *a, **k: False)
    monkeypatch.setattr(guards, "has_entry_for_checkout", lambda *a, **k: True)
    monkeypatch.setattr(guards, "work_log_closed_hour_to", lambda *a, **k: None)
    monkeypatch.setattr(
        guards,
        "normalize_overnight_checkout_reference",
        lambda **k: (k["reference_date_iso"], k.get("event_at")),
    )
    reason = guards.new_card_punch_blocked_reason(
        intent="card_check_out_now",
        employer_afm="123",
        branch_aa="0",
        employee_afm="111222333",
        reference_date_iso="2026-08-18",
    )
    assert reason is None


def test_new_card_punch_blocked_reason_rejects_future_date():
    reason = guards.new_card_punch_blocked_reason(
        intent="card_check_in_now",
        employer_afm="123456789",
        branch_aa="0",
        employee_afm="111222333",
        reference_date_iso="2099-01-01",
    )
    assert reason == "Η ώρα κίνησης δεν μπορεί να είναι μελλοντική"


def test_new_card_punch_blocked_reason_rejects_future_time_today():
    from datetime import datetime, timedelta

    from app.work_card_payload import tz_athens

    future = datetime.now(tz_athens()) + timedelta(hours=2)
    reason = guards.new_card_punch_blocked_reason(
        intent="card_check_in_retro",
        employer_afm="123456789",
        branch_aa="0",
        employee_afm="111222333",
        reference_date_iso=future.date().isoformat(),
        event_at=future.isoformat(timespec="seconds"),
    )
    assert reason == "Η ώρα κίνησης δεν μπορεί να είναι μελλοντική"
