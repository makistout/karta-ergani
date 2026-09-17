"""Unit tests for home contract compliance alerts."""

from __future__ import annotations

from datetime import date

from app.contract_home_alerts import (
    CODE_HOURS_OVER,
    CODE_LEAVE_OVER,
    CODE_SIXTH_DAY,
    _alerts_for_employee_day,
    _schedule_import_contract_warnings,
)


def _slot(day: str, hour_from: str, hour_to: str, shift_type: str = "ΕΡΓΑΣΙΑ") -> dict:
    return {
        "work_date": day,
        "hour_from": hour_from,
        "hour_to": hour_to,
        "shift_type": shift_type,
        "employee_afm": "123456789",
    }


def test_sixth_day_alert_for_five_day_contract():
    # Mon 15/09/2026 .. focus Sat 20/09/2026 = 6 work days on 5-day contract
    week = {
        ("123456789", "15/09/2026"): [_slot("15/09/2026", "09:00", "17:00")],
        ("123456789", "16/09/2026"): [_slot("16/09/2026", "09:00", "17:00")],
        ("123456789", "17/09/2026"): [_slot("17/09/2026", "09:00", "17:00")],
        ("123456789", "18/09/2026"): [_slot("18/09/2026", "09:00", "17:00")],
        ("123456789", "19/09/2026"): [_slot("19/09/2026", "09:00", "17:00")],
        ("123456789", "20/09/2026"): [_slot("20/09/2026", "09:00", "17:00")],
    }
    contract = {
        "weekly_work_days": "5",
        "weekly_hours": "40",
        "characterization": "Πλήρης απασχόληση",
    }
    alerts = _alerts_for_employee_day(
        afm="123456789",
        focus=date(2026, 9, 20),
        focus_ergani="20/09/2026",
        contract=contract,
        week_slots=week,
        leave_taken=None,
        row={},
    )
    codes = {a["code"] for a in alerts}
    assert CODE_SIXTH_DAY in codes
    assert CODE_HOURS_OVER in codes  # 6*8h = 48 > 40


def test_hours_over_uses_total_weekly_hours_not_partial_weekly():
    """ΣΚΟΡΔΑ: weekly_hours=12 αλλά Συνολικές=28 → όριο 28, όχι ψευδές alert στα 13."""
    week = {
        ("123456789", "15/09/2026"): [_slot("15/09/2026", "17:00", "00:00")],
        ("123456789", "16/09/2026"): [_slot("16/09/2026", "17:00", "00:00")],
    }
    # 7+7 = 14ώ < 28ώ Συνολικές
    contract = {
        "weekly_work_days": "5-ήμερο",
        "weekly_hours": "12,0",
        "total_weekly_hours": "28,0",
        "fulltime_contract_weekly_hours": "40,0",
        "characterization": "Μερική απασχόληση",
    }
    alerts = _alerts_for_employee_day(
        afm="123456789",
        focus=date(2026, 9, 15),
        focus_ergani="15/09/2026",
        contract=contract,
        week_slots=week,
        leave_taken=None,
        row={},
    )
    assert not any(a["code"] == CODE_HOURS_OVER for a in alerts)


def test_hours_over_label_says_hours_not_clock():
    week = {
        ("123456789", "15/09/2026"): [_slot("15/09/2026", "08:00", "18:00")],
        ("123456789", "16/09/2026"): [_slot("16/09/2026", "08:00", "18:00")],
        ("123456789", "17/09/2026"): [_slot("17/09/2026", "08:00", "18:00")],
        ("123456789", "18/09/2026"): [_slot("18/09/2026", "08:00", "18:00")],
        ("123456789", "19/09/2026"): [_slot("19/09/2026", "08:00", "18:00")],
    }
    contract = {
        "weekly_work_days": "5",
        "total_weekly_hours": "40",
        "characterization": "Πλήρης απασχόληση",
    }
    alerts = _alerts_for_employee_day(
        afm="123456789",
        focus=date(2026, 9, 19),
        focus_ergani="19/09/2026",
        contract=contract,
        week_slots=week,
        leave_taken=None,
        row={},
    )
    hours = [a for a in alerts if a["code"] == CODE_HOURS_OVER]
    assert hours
    assert "ώρες" in hours[0]["label"]
    assert "Συνολικές" in hours[0]["label"]


def test_leave_over_when_entitlement_exhausted():
    week = {
        ("123456789", "16/09/2026"): [
            _slot("16/09/2026", "", "", shift_type="ΑΔΕΙΑ ΚΑΝΟΝΙΚΗ")
        ],
    }
    # Empty hour_from/to — _working_slots empty, but shift_type has ΑΔΕΙΑ
    # _day_state needs slots with shift_type ΑΔΕΙΑ
    week[("123456789", "16/09/2026")] = [{
        "work_date": "16/09/2026",
        "hour_from": None,
        "hour_to": None,
        "shift_type": "ΑΔΕΙΑ",
        "employee_afm": "123456789",
    }]
    contract = {
        "weekly_work_days": "5",
        "weekly_hours": "40",
        "characterization": "Πλήρης απασχόληση",
    }
    alerts = _alerts_for_employee_day(
        afm="123456789",
        focus=date(2026, 9, 16),
        focus_ergani="16/09/2026",
        contract=contract,
        week_slots=week,
        leave_taken=22,
        row={},
    )
    assert any(a["code"] == CODE_LEAVE_OVER for a in alerts)
    assert "22" in alerts[0]["label"] or "23" in alerts[0]["label"]


def test_no_alert_when_within_contract():
    week = {
        ("123456789", "15/09/2026"): [_slot("15/09/2026", "09:00", "17:00")],
        ("123456789", "16/09/2026"): [_slot("16/09/2026", "09:00", "17:00")],
        ("123456789", "17/09/2026"): [_slot("17/09/2026", "09:00", "17:00")],
        ("123456789", "18/09/2026"): [_slot("18/09/2026", "09:00", "17:00")],
        ("123456789", "19/09/2026"): [_slot("19/09/2026", "09:00", "17:00")],
    }
    contract = {
        "weekly_work_days": "5",
        "weekly_hours": "40",
        "characterization": "Πλήρης απασχόληση",
    }
    alerts = _alerts_for_employee_day(
        afm="123456789",
        focus=date(2026, 9, 19),
        focus_ergani="19/09/2026",
        contract=contract,
        week_slots=week,
        leave_taken=10,
        row={},
    )
    assert alerts == []


def _import_row(day: str, hour_from: str = "09:00", hour_to: str = "17:00") -> dict:
    return {
        "work_date": day,
        "employee_afm": "123456789",
        "eponymo": "ΔΟΚΙΜΗ",
        "onoma": "ΕΡΓΑΖΟΜΕΝΟΣ",
        "import_action": "work",
        "change_kind": "update",
        "validation_errors": [],
        "proposed_snapshot": [{
            "hour_from": hour_from,
            "hour_to": hour_to,
            "shift_type": "ΕΡΓ",
            "schedule_type": "ΕΡΓ",
        }],
    }


def test_schedule_import_groups_contract_warnings_per_employee():
    rows = [
        _import_row(f"{day:02d}/09/2026")
        for day in range(14, 20)  # Monday through Saturday: 6 * 8h
    ]
    warnings = _schedule_import_contract_warnings(
        rows,
        contracts={"123456789": {
            "weekly_work_days": "5",
            "total_weekly_hours": "40",
            "characterization": "Πλήρης απασχόληση",
        }},
        schedule_rows=[],
        leave_map={},
    )

    assert len(warnings) == 1
    assert warnings[0]["employee_afm"] == "123456789"
    assert {alert["code"] for alert in warnings[0]["alerts"]} == {
        CODE_SIXTH_DAY,
        CODE_HOURS_OVER,
    }


def test_schedule_import_rest_replaces_existing_work_before_check():
    existing = [
        _slot(f"{day:02d}/09/2026", "09:00", "17:00")
        for day in range(14, 20)
    ]
    rest_row = {
        "work_date": "19/09/2026",
        "employee_afm": "123456789",
        "eponymo": "ΔΟΚΙΜΗ",
        "onoma": "ΕΡΓΑΖΟΜΕΝΟΣ",
        "import_action": "rest",
        "change_kind": "update",
        "validation_errors": [],
        "proposed_snapshot": [{
            "hour_from": None,
            "hour_to": None,
            "shift_type": "ΑΝ",
            "schedule_type": "ΑΝ",
        }],
    }
    warnings = _schedule_import_contract_warnings(
        [rest_row],
        contracts={"123456789": {
            "weekly_work_days": "5",
            "total_weekly_hours": "40",
            "characterization": "Πλήρης απασχόληση",
        }},
        schedule_rows=existing,
        leave_map={},
    )

    assert warnings == []


def test_schedule_import_checks_existing_leave_on_unchanged_day():
    leave_day = {
        "work_date": "16/09/2026",
        "employee_afm": "123456789",
        "hour_from": None,
        "hour_to": None,
        "shift_type": "ΑΔΕΙΑ",
    }
    unchanged_row = {
        "work_date": "16/09/2026",
        "employee_afm": "123456789",
        "eponymo": "ΔΟΚΙΜΗ",
        "onoma": "ΕΡΓΑΖΟΜΕΝΟΣ",
        "import_action": "skip",
        "change_kind": "skip",
        "validation_errors": [],
        "proposed_snapshot": [],
    }
    warnings = _schedule_import_contract_warnings(
        [unchanged_row],
        contracts={"123456789": {
            "weekly_work_days": "5",
            "total_weekly_hours": "40",
            "characterization": "Πλήρης απασχόληση",
        }},
        schedule_rows=[leave_day],
        leave_map={"123456789": {"days_taken": 22}},
    )

    assert len(warnings) == 1
    assert [alert["code"] for alert in warnings[0]["alerts"]] == [CODE_LEAVE_OVER]
