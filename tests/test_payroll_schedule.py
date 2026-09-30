from datetime import date
from decimal import Decimal
import pytest

from app.payroll import payroll_for_employee, default_parameter_map, build_payroll_report
from app.payroll_schedule import scheduled_salary_units


def row(day="12/09/2026", start="18:00", end="00:00", **extra):
    return {"work_date": day, "hour_from": start, "hour_to": end, **extra}


def contract(**extra):
    return {"salary": "155,10", "weekly_hours": "6,0", "weekly_work_days": "5-ήμερη",
            "characterization": "1", "hire_date": "2026-09-12", "fixed_term_to": "13/09/2026", **extra}


def calculate(rows, **extra):
    return payroll_for_employee(employee={"employee_afm": "111111111"}, contract=contract(**extra),
        params=default_parameter_map(), period_from=date(2026,9,1), period_to=date(2026,9,30), schedule_rows=rows)


def test_real_weekend_case_uses_six_declared_hours_not_weekdays():
    result = calculate([row(), row("13/09/2026", "", "")])
    assert result["salary_schedule_minutes"] == 360
    assert result["salary_payable_days"] == 6
    assert result["period_salary"] == 37.22
    assert result["salary_schedule_dates"] == ["2026-09-12"]


def test_sunday_only_and_weekday_rest():
    result = calculate([row("13/09/2026"), row("12/09/2026", "", "", shift_type="ΑΝΑΠΑΥΣΗ")])
    assert result["period_salary"] == 37.22


def test_split_and_duplicate_intervals_not_double_counted():
    rows = [row(start="10:00", end="13:00"), row(start="18:00", end="21:00")]
    assert calculate(rows + rows)["period_salary"] == 37.22


def test_external_break_subtracted_once_and_paid_break_preserved():
    shift = row(break_minutes=30, break_in_work=0)
    assert calculate([shift, shift])["salary_schedule_minutes"] == 330
    assert calculate([row(break_minutes=30, break_in_work=1)])["salary_schedule_minutes"] == 360


def test_weekly_cap_and_relationship_bounds():
    shifts = [row("11/09/2026"), row(), row("13/09/2026"), row("14/09/2026")]
    result = calculate(shifts)
    assert result["salary_schedule_minutes"] == 360
    assert result["salary_schedule_dates"] == ["2026-09-12", "2026-09-13"]


@pytest.mark.parametrize("rows", [None, [], [row(start="bad")],
    [row(start="", end="", shift_type="ΑΔΕΙΑ")], [row(start="", end="", shift_type="ΕΡΓΑΣΙΑ")]])
def test_missing_or_ambiguous_schedule_rejected_instead_of_guessing(rows):
    with pytest.raises(ValueError):
        calculate(rows)


def test_explicit_rest_can_produce_zero_and_full_month_keeps_salary():
    assert calculate([row(start="", end="", shift_type="ΡΕΠΟ")])["period_salary"] == 0
    assert calculate(None, hire_date="2026-09-01", fixed_term_to="30/09/2026")["period_salary"] == 155.10


def test_report_filters_schedule_by_employee_and_normalizes_afm():
    result = build_payroll_report({"employees": [{"employee_afm": "012345678"}]},
        {"012345678": contract()}, default_parameter_map(), period_from=date(2026,9,1),
        period_to=date(2026,9,30), schedule_rows=[row(employee_afm="12345678"),
            row("13/09/2026", employee_afm="999999999")])
    assert result["employees"][0]["period_salary"] == 37.22
