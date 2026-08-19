from datetime import date

from app.timekeeping import build_timekeeping_report


def _row(**overrides):
    row = {
        "employee_afm": "123456789", "eponymo": "ΔΟΚΙΜΗ", "onoma": "ΕΝΑ",
        "work_date": "17/08/2026", "status": "ok", "declared": "09:00–17:00",
        "proposed": "09:00–17:00", "punch_count": 2, "break_minutes": 0,
        "overtime_minutes": 0,
    }
    row.update(overrides)
    return row


def test_change_uses_effective_proposed_schedule():
    report = build_timekeeping_report([_row(status="change", proposed="10:00–18:00")])
    day = report["days"][0]
    assert day["basis_source"] == "effective_proposed"
    assert day["basis_label"] == "10:00–18:00"


def test_no_punch_uses_declared_basis():
    day = build_timekeeping_report([_row(punch_count=0)])["days"][0]
    assert day["basis_source"] == "declared_no_punch"
    assert day["recognized_work_minutes"] == 480


def test_break_is_contiguous_and_prefers_first_non_premium_point():
    day = build_timekeeping_report([_row(declared="21:00–23:00", break_minutes=30)])["days"][0]
    assert day["break_interval"] == "21:01–21:31"
    assert day["premium_minutes"]["day"] == 30
    assert day["premium_minutes"]["night"] == 60


def test_overnight_sunday_and_night_overlap_are_partitioned():
    row = _row(work_date="16/08/2026", declared="21:00–01:00")  # Sunday
    day = build_timekeeping_report([row])["days"][0]
    assert day["premium_minutes"]["sunday_holiday"] == 60
    assert day["premium_minutes"]["night_sunday_holiday"] == 120
    assert day["premium_minutes"]["night"] == 60


def test_holiday_is_treated_like_sunday():
    row = _row(work_date="17/08/2026", declared="09:00–10:00")
    day = build_timekeeping_report([row], holidays={date(2026, 8, 17)})["days"][0]
    assert day["premium_minutes"]["sunday_holiday"] == 60


def test_overtime_crossing_annual_limit_splits_40_and_60():
    context = {"123456789": {"legal_overtime_minutes_before_period": 149 * 60 + 30, "data_complete": True}}
    day = build_timekeeping_report([_row(overtime_minutes=90)], annual_context_by_employee=context)["days"][0]
    assert day["overtime_40"] == 30
    assert day["overtime_60"] == 60


def test_overtime_after_four_daily_hours_is_120():
    day = build_timekeeping_report([_row(overtime_minutes=300)])["days"][0]
    assert day["overtime_40"] == 240
    assert day["overtime_120"] == 60


def test_review_blocks_timekeeping():
    try:
        build_timekeeping_report([_row(status="review")])
    except ValueError as exc:
        assert "έλεγχο" in str(exc)
    else:
        raise AssertionError("review row should block timekeeping")


def test_six_days_do_not_create_sixth_day_band():
    rows = [_row(work_date=f"{day:02d}/08/2026") for day in range(17, 23)]
    report = build_timekeeping_report(rows)
    assert sum(day["sixth_day_minutes"] for day in report["days"]) == 0


def test_seven_days_mark_sunday_as_sixth_day():
    rows = [_row(work_date=f"{day:02d}/08/2026") for day in range(17, 24)]
    report = build_timekeeping_report(rows)
    sunday = next(day for day in report["days"] if day["work_date"] == "23/08/2026")
    assert sunday["sixth_day_minutes"] == 480


def test_partial_extra_is_allocated_only_from_weekly_excess():
    rows = [
        _row(work_date=f"{day:02d}/08/2026", contract_kind="Μερική", weekly_days=5,
             contract_weekly_minutes=1200, declared="09:00–14:00")
        for day in range(17, 22)
    ]
    report = build_timekeeping_report(rows)
    assert sum(day["partial_additional_12"] for day in report["days"]) == 300


def test_partial_above_full_daily_cap_is_120():
    rows = [_row(contract_kind="Μερική", weekly_days=5, contract_weekly_minutes=1200,
                 declared="09:00–18:00")]
    day = build_timekeeping_report(rows)["days"][0]
    assert day["partial_120"] == 60


def test_special_arrangement_does_not_finalize_overtime_category():
    day = build_timekeeping_report([_row(overtime_minutes=90, work_arrangement=True)])["days"][0]
    assert day["overtime_40"] == 0
    assert any("Ειδικό καθεστώς" in warning for warning in day["warnings"])
