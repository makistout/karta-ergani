from datetime import date
from unittest.mock import patch

from flask import Flask

from app.routes_employees import (
    NO_SPECIALTY_LABEL,
    _resolve_employees_stats_month,
    _specialty_label,
    employees_list,
)


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return date(2026, 9, 28)


def test_defaults_to_current_month_as_of_today():
    year, month, as_of = _resolve_employees_stats_month(today=date(2026, 9, 28))
    assert (year, month, as_of) == (2026, 9, date(2026, 9, 28))


def test_past_month_as_of_is_last_day():
    year, month, as_of = _resolve_employees_stats_month(
        year=2026, month=6, today=date(2026, 9, 28),
    )
    assert (year, month, as_of) == (2026, 6, date(2026, 6, 30))


def test_clamps_future_month_to_current():
    year, month, as_of = _resolve_employees_stats_month(
        year=2026, month=12, today=date(2026, 9, 28),
    )
    assert (year, month, as_of) == (2026, 9, date(2026, 9, 28))


def test_clamps_older_than_six_months():
    year, month, as_of = _resolve_employees_stats_month(
        year=2026, month=2, today=date(2026, 9, 28),
    )
    assert (year, month, as_of) == (2026, 3, date(2026, 3, 31))


def test_invalid_month_falls_back_to_current():
    year, month, as_of = _resolve_employees_stats_month(
        year="xx", month=9, today=date(2026, 9, 28),
    )
    assert (year, month, as_of) == (2026, 9, date(2026, 9, 28))


def test_cross_year_six_months_back():
    year, month, as_of = _resolve_employees_stats_month(
        year=2025, month=10, today=date(2026, 1, 15),
    )
    assert (year, month, as_of) == (2025, 10, date(2025, 10, 31))


def test_too_old_cross_year_clamps_to_july():
    year, month, as_of = _resolve_employees_stats_month(
        year=2025, month=6, today=date(2026, 1, 15),
    )
    assert (year, month) == (2025, 7)
    assert as_of == date(2025, 7, 31)


def test_specialty_label_fallback():
    assert _specialty_label(None) == NO_SPECIALTY_LABEL
    assert _specialty_label({}) == NO_SPECIALTY_LABEL
    assert _specialty_label({"specialty": "  ΣΕΡΒΙΤΟΡΟΣ  "}) == "ΣΕΡΒΙΤΟΡΟΣ"


def test_employees_list_uses_selected_month_for_open_and_leave():
    app = Flask(__name__)
    captured: dict = {}

    def fake_punches(_employer, _branch, *, year=None, month=None, store_id=None):
        captured["punches"] = (year, month)
        captured["store_id"] = store_id
        return {"111222333": 2}

    def fake_leave(*, store_id, employee_afms, today=None):
        captured["leave_today"] = today
        return {"111222333": {"days_taken": 4}}

    with patch("app.routes_employees.date", _FrozenDate), \
         patch("app.routes_employees.resolve_active_store", return_value={
             "id": 7, "name": "ERATO", "employer_afm": "123456789", "branch_aa": "0",
         }), \
         patch("app.routes_employees.list_employees_for_employer", return_value=[{
             "afm": "111222333", "eponymo": "ΠΑΠΑΔΟΠΟΥΛΟΣ", "onoma": "ΓΙΩΡΓΟΣ", "active": True,
         }]), \
         patch("app.routes_employees.list_current_for_store", return_value=[{
             "employee_afm": "111222333",
             "specialty": "ΣΕΡΒΙΤΟΡΟΣ",
             "weekly_work_days": "5",
         }]), \
         patch(
             "app.routes_employees.count_incomplete_punches_by_employee_for_month",
             side_effect=fake_punches,
         ), \
         patch(
             "app.routes_employees.load_current_year_normal_leave",
             side_effect=fake_leave,
         ):
        with app.test_request_context("/api/employees/list?year=2026&month=6"):
            response = employees_list()

    data = response.get_json()
    assert captured["punches"] == (2026, 6)
    assert captured["store_id"] == 7
    assert captured["leave_today"] == date(2026, 6, 30)
    emp = data["employees"][0]
    assert emp["specialty"] == "ΣΕΡΒΙΤΟΡΟΣ"
    assert emp["open_punches_month"] == 2
    assert emp["normal_leave_days_taken"] == 4
    assert emp["normal_leave_entitled_days"] == 22
    assert data["year"] == 2026
    assert data["month"] == 6
    assert data["open_punches_month_label"] == "06/2026"
    assert data["normal_leave_latest_month"] == "06/2026"
