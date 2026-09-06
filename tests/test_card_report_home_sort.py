"""Σειρά γραμμών αρχικής: είσοδος → ωράριο → αλφαβητικά."""

from app.card_report import home_report_sort_key


def test_home_sort_entry_punch_before_schedule_and_alpha():
    with_entry_late = {
        "employee_afm": "1",
        "eponymo": "ΑΑΑ",
        "work_log": {"hour_from": "11:00"},
        "schedule": {"hour_from": "09:00", "hour_to": "17:00"},
    }
    with_entry_early = {
        "employee_afm": "2",
        "eponymo": "ΩΩΩ",
        "work_log": {"hour_from": "08:30"},
        "schedule": {"hour_from": "10:00", "hour_to": "18:00"},
    }
    schedule_only = {
        "employee_afm": "3",
        "eponymo": "ΜΜΜ",
        "work_log": None,
        "schedule": {"hour_from": "09:00", "hour_to": "17:00"},
    }
    schedule_later = {
        "employee_afm": "4",
        "eponymo": "ΒΒΒ",
        "work_log": {},
        "schedule": {"hour_from": "12:00", "hour_to": "20:00"},
    }
    alpha_b = {
        "employee_afm": "5",
        "eponymo": "Βήτα",
        "work_log": None,
        "schedule": None,
    }
    alpha_a = {
        "employee_afm": "6",
        "eponymo": "Άλφα",
        "card": {},
        "schedule": {"hour_from": "", "hour_to": "", "shift_type": ""},
    }
    rows = [
        with_entry_late,
        schedule_later,
        alpha_b,
        with_entry_early,
        schedule_only,
        alpha_a,
    ]
    ordered = sorted(rows, key=home_report_sort_key)
    assert [r["employee_afm"] for r in ordered] == ["2", "1", "3", "4", "6", "5"]


def test_home_sort_card_check_in_counts_as_entry():
    row = {
        "employee_afm": "9",
        "eponymo": "ΤΕΣΤ",
        "work_log": None,
        "card": {"check_in": "07:15:00", "has_check_in": True},
        "schedule": {"hour_from": "10:00", "hour_to": "18:00"},
    }
    assert home_report_sort_key(row)[0] == 0
    assert home_report_sort_key(row)[1] == 7 * 60 + 15
