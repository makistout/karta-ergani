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
