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
    assert day["effective_declared"] == "10:00–18:00"
    assert day["declared"] == "09:00–17:00"


def test_change_to_rest_replaces_payroll_declaration_but_has_no_recognized_interval():
    day = build_timekeeping_report([
        _row(status="change", proposed="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", punch_count=0)
    ])["days"][0]
    assert day["effective_declared"] == "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
    assert day["declared"] == "09:00–17:00"
    assert day["basis_label"] == ""
    assert day["recognized_work_minutes"] == 0


def test_no_punch_uses_declared_basis():
    day = build_timekeeping_report([_row(punch_count=0)])["days"][0]
    assert day["basis_source"] == "declared_no_punch"
    assert day["recognized_work_minutes"] == 480


def test_leave_is_excluded_from_timekeeping_entirely():
    report = build_timekeeping_report([
        _row(day_state="Άδεια", declared="ΑΔΕΙΑ", proposed="ΑΔΕΙΑ", punch_count=0)
    ])
    assert report["days"] == []
    assert report["employees"] == []
    assert report["counts"] == {"days": 0, "employees": 0}


def test_approved_change_from_leave_to_work_is_included_by_effective_proposal():
    day = build_timekeeping_report([
        _row(status="change", day_state="Άδεια", declared="ΑΔΕΙΑ", proposed="09:00–17:00")
    ])["days"][0]
    assert day["effective_declared"] == "09:00–17:00"
    assert day["recognized_work_minutes"] == 480


def test_non_working_day_does_not_warn_that_break_cannot_fit():
    day = build_timekeeping_report([
        _row(status="change", proposed="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", punch_count=0, break_minutes=30)
    ])["days"][0]
    assert day["recognized_work_minutes"] == 0
    assert day["warnings"] == []


def test_overwork_and_overtime_are_split_by_actual_premium_zone():
    row = _row(
        work_date="16/08/2026", status="change", proposed="14:30–22:30",
        declared="14:30–22:30", contract_kind="Πλήρης", weekly_days=5,
        overwork_minutes=60, overtime_minutes=120,
        overtime_segments=[{
            "date": "16/08/2026", "from": "23:30", "to": "01:30", "minutes": 120,
        }],
    )
    day = build_timekeeping_report([row])["days"][0]
    assert day["overwork_breakdown"] == {
        "day": 0, "night": 0, "sunday_holiday": 0, "night_sunday_holiday": 60,
    }
    assert day["overtime_40_breakdown"] == {
        "day": 0, "night": 90, "sunday_holiday": 0, "night_sunday_holiday": 30,
    }


def test_annual_150_hour_boundary_preserves_chronological_premium_breakdown():
    context = {"123456789": {
        "legal_overtime_minutes_before_period": 149 * 60 + 30, "data_complete": True,
    }}
    row = _row(
        work_date="16/08/2026", status="change", proposed="14:30–22:30",
        declared="14:30–22:30", overtime_minutes=90,
        overtime_segments=[{
            "date": "16/08/2026", "from": "23:30", "to": "01:00", "minutes": 90,
        }],
    )
    day = build_timekeeping_report([row], annual_context_by_employee=context)["days"][0]
    assert day["overtime_40_breakdown"]["night_sunday_holiday"] == 30
    assert day["overtime_60_breakdown"]["night"] == 60


def test_sixth_day_base_is_removed_from_ordinary_premium_buckets():
    rows = [
        _row(
            work_date=f"{day:02d}/08/2026", declared="09:00–17:00",
            proposed="09:00–17:00", contract_kind="Πλήρης", weekly_days=5,
        )
        for day in range(3, 9)
    ]
    report = build_timekeeping_report(rows)
    sixth = next(day for day in report["days"] if day["sixth_day_minutes"])
    assert sixth["work_date"] == "08/08/2026"
    assert sum(sixth["premium_minutes"].values()) == 0
    assert sum(sixth["sixth_day_breakdown"].values()) == 480
    assert sixth["base_allocation_integrity_minutes"] == 480


def test_rotating_multiple_extra_days_are_selected_from_sunday_towards_monday():
    rows = [
        _row(
            work_date=f"{day:02d}/08/2026", declared="09:00–17:00",
            proposed="09:00–17:00", contract_kind="Εκ περιτροπής", weekly_days=3,
        )
        for day in range(3, 8)
    ]
    report = build_timekeeping_report(rows)
    extras = [day for day in report["days"] if day["rotation_extra_day"]]
    assert [day["work_date"] for day in extras] == ["06/08/2026", "07/08/2026"]
    for day in extras:
        assert day["partial_additional_12"] == 480
        assert sum(day["premium_minutes"].values()) == 0
        assert sum(day["partial_additional_12_breakdown"].values()) == 480
        assert day["base_allocation_integrity_minutes"] == 480


def test_rotating_extra_day_splits_12_and_120_and_keeps_zones_exclusive():
    rows = [
        _row(
            work_date=f"{day:02d}/08/2026", declared="09:00–17:00",
            proposed="09:00–17:00", contract_kind="Εκ περιτροπής", weekly_days=5,
        )
        for day in range(3, 9)
    ]
    rows.append(_row(
        work_date="09/08/2026", declared="20:00–06:00", proposed="20:00–06:00",
        contract_kind="Εκ περιτροπής", weekly_days=5,
    ))
    report = build_timekeeping_report(rows)
    sunday = next(day for day in report["days"] if day["work_date"] == "09/08/2026")
    saturday = next(day for day in report["days"] if day["work_date"] == "08/08/2026")
    assert sunday["rotation_extra_day"] is True
    assert saturday["rotation_extra_day"] is True
    assert sunday["partial_additional_12"] == 480
    assert sunday["partial_120"] == 120
    assert sum(sunday["premium_minutes"].values()) == 0
    assert sum(sunday["partial_additional_12_breakdown"].values()) == 480
    assert sum(sunday["partial_120_breakdown"].values()) == 120
    assert sunday["base_allocation_integrity_minutes"] == 600


def test_partial_employment_never_generates_40_or_60_overtime():
    day = build_timekeeping_report([_row(
        contract_kind="Μερική", weekly_days=5, contract_weekly_minutes=1200,
        declared="09:00–13:00", proposed="09:00–13:00", overtime_minutes=120,
        overtime_segments=[{"date": "17/08/2026", "from": "13:00", "to": "15:00", "minutes": 120}],
    )])["days"][0]
    assert day["overtime_40"] == 0
    assert day["overtime_60"] == 0
    assert day["overtime_120"] == 0


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


def test_holiday_without_punch_has_no_premium_when_store_does_not_work_sundays():
    row = _row(work_date="17/08/2026", declared="09:00–10:00", punch_count=0)
    day = build_timekeeping_report(
        [row], holidays={date(2026, 8, 17)}, sunday_work_enabled=False,
    )["days"][0]
    assert day["premium_minutes"]["sunday_holiday"] == 0
    assert day["premium_minutes"]["day"] == 60


def test_holiday_without_punch_keeps_premium_when_store_works_sundays():
    row = _row(work_date="17/08/2026", declared="09:00–10:00", punch_count=0)
    day = build_timekeeping_report(
        [row], holidays={date(2026, 8, 17)}, sunday_work_enabled=True,
    )["days"][0]
    assert day["premium_minutes"]["sunday_holiday"] == 60


def test_sunday_without_punch_always_uses_recognized_basis_for_premium():
    row = _row(work_date="23/08/2026", declared="09:00–10:00", punch_count=0)
    day = build_timekeeping_report([row], sunday_work_enabled=False)["days"][0]
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
    rows = [
        _row(work_date=f"{day:02d}/08/2026", declared="09:00–15:00", contract_kind="Πλήρης")
        for day in range(17, 23)
    ]
    report = build_timekeeping_report(rows)
    assert sum(day["sixth_day_minutes"] for day in report["days"]) == 0


def test_seven_equal_days_mark_sunday_then_saturday_as_at_most_two_sixth_days():
    rows = [_row(work_date=f"{day:02d}/08/2026", contract_kind="Πλήρης") for day in range(17, 24)]
    report = build_timekeeping_report(rows)
    marked = [day["work_date"] for day in report["days"] if day["sixth_day_minutes"]]
    assert marked == ["22/08/2026", "23/08/2026"]


def test_six_days_above_40_hours_mark_only_shortest_tie_priority_day():
    rows = [_row(work_date=f"{day:02d}/08/2026", contract_kind="Πλήρης") for day in range(17, 23)]
    report = build_timekeeping_report(rows)
    marked = [day["work_date"] for day in report["days"] if day["sixth_day_minutes"]]
    assert marked == ["22/08/2026"]


def test_seven_days_choose_shortest_before_sunday_priority():
    rows = [
        _row(work_date=f"{day:02d}/08/2026", contract_kind="Πλήρης",
             declared="09:00–11:00" if day == 19 else "09:00–17:00")
        for day in range(17, 24)
    ]
    report = build_timekeeping_report(rows)
    marked = [day["work_date"] for day in report["days"] if day["sixth_day_minutes"]]
    assert marked == ["19/08/2026", "23/08/2026"]


def test_next_week_three_explicit_rests_suppress_any_sixth_day_when_sunday_over_five_hours():
    rows = [_row(work_date=f"{day:02d}/08/2026", contract_kind="Πλήρης") for day in range(17, 24)]
    report = build_timekeeping_report(
        rows,
        sunday_work_enabled=False,
        next_week_context_by_employee={
            "123456789": {"known": True, "explicit_rest_days": 3},
        },
    )
    assert sum(day["sixth_day_minutes"] for day in report["days"]) == 0


def test_exactly_five_sunday_hours_do_not_trigger_next_week_rest_exemption():
    rows = [
        _row(work_date=f"{day:02d}/08/2026", contract_kind="Πλήρης",
             declared="09:00–14:00" if day == 23 else "09:00–17:00")
        for day in range(17, 24)
    ]
    report = build_timekeeping_report(
        rows,
        sunday_work_enabled=False,
        next_week_context_by_employee={"123456789": {"known": True, "explicit_rest_days": 3}},
    )
    assert sum(day["sixth_day_minutes"] for day in report["days"]) > 0


def test_sixth_day_breakdown_splits_sunday_night_at_midnight():
    work_dates = ("17/08/2026", "18/08/2026", "19/08/2026", "20/08/2026", "21/08/2026")
    rows = [_row(work_date=value, contract_kind="Πλήρης") for value in work_dates]
    rows.append(_row(work_date="23/08/2026", contract_kind="Πλήρης", declared="23:00–01:00"))
    report = build_timekeeping_report(rows, sunday_work_enabled=True)
    sunday = next(day for day in report["days"] if day["work_date"] == "23/08/2026")
    assert sunday["sixth_day_minutes"] == 120
    assert sunday["sixth_day_breakdown"] == {
        "day": 0, "night": 60, "sunday_holiday": 0, "night_sunday_holiday": 60,
    }


def test_sixth_day_contains_only_clean_basis_not_overtime():
    rows = [
        _row(work_date=f"{day:02d}/08/2026", contract_kind="Πλήρης", overtime_minutes=60)
        for day in range(17, 23)
    ]
    report = build_timekeeping_report(rows)
    sixth = next(day for day in report["days"] if day["sixth_day_minutes"])
    assert sixth["sixth_day_minutes"] == 480
    assert sixth["overtime_40"] == 60


def test_unknown_next_week_does_not_suppress_sixth_day():
    rows = [_row(work_date=f"{day:02d}/08/2026", contract_kind="Πλήρης") for day in range(17, 24)]
    report = build_timekeeping_report(
        rows,
        sunday_work_enabled=False,
        next_week_context_by_employee={
            "123456789": {"known": False, "explicit_rest_days": 3},
        },
    )
    assert sum(day["sixth_day_minutes"] for day in report["days"]) > 0


def test_sixth_day_rule_does_not_apply_to_partial_contract():
    rows = [
        _row(work_date=f"{day:02d}/08/2026", contract_kind="Μερική", weekly_days=5,
             contract_weekly_minutes=1200)
        for day in range(17, 24)
    ]
    report = build_timekeeping_report(rows)
    assert sum(day["sixth_day_minutes"] for day in report["days"]) == 0


def test_partial_extra_is_allocated_only_from_weekly_excess():
    rows = [
        _row(work_date=f"{day:02d}/08/2026", contract_kind="Μερική", weekly_days=5,
             contract_weekly_minutes=1200, declared="09:00–14:00")
        for day in range(17, 22)
    ]
    report = build_timekeeping_report(rows)
    assert sum(day["partial_additional_12"] for day in report["days"]) == 300


def test_partial_extra_is_allocated_from_sunday_back_to_monday_with_tail_intervals():
    durations = {
        "17/08/2026": "09:00–15:00",  # Monday: 2 h above imputed base
        "18/08/2026": "09:00–13:00",
        "19/08/2026": "09:00–13:00",
        "20/08/2026": "09:00–13:00",
        "23/08/2026": "09:00–14:00",  # Sunday: 1 h above imputed base
    }
    rows = [
        _row(work_date=work_date, declared=declared, contract_kind="Μερική",
             weekly_days=5, contract_weekly_minutes=1200)
        for work_date, declared in durations.items()
    ]
    days = {day["work_date"]: day for day in build_timekeeping_report(rows)["days"]}
    assert days["23/08/2026"]["partial_additional_12"] == 60
    assert days["23/08/2026"]["partial_additional_12_intervals"] == ["13:00–14:00"]
    assert days["17/08/2026"]["partial_additional_12"] == 120
    assert days["17/08/2026"]["partial_additional_12_intervals"] == ["13:00–15:00"]


def test_partial_extra_fallback_uses_last_workday_then_moves_backwards():
    rows = [
        _row(work_date=work_date, declared="09:00–13:00", contract_kind="Μερική",
             weekly_days=5, contract_weekly_minutes=1200)
        for work_date in ("17/08/2026", "18/08/2026", "19/08/2026", "20/08/2026", "21/08/2026", "23/08/2026")
    ]
    days = {day["work_date"]: day for day in build_timekeeping_report(rows)["days"]}
    assert sum(day["partial_additional_12"] for day in days.values()) == 240
    assert days["23/08/2026"]["partial_additional_12"] == 240
    assert days["23/08/2026"]["partial_additional_12_intervals"] == ["09:00–13:00"]


def test_partial_above_full_daily_cap_is_120():
    rows = [_row(contract_kind="Μερική", weekly_days=5, contract_weekly_minutes=1200,
                 declared="09:00–18:00")]
    day = build_timekeeping_report(rows)["days"][0]
    assert day["partial_120"] == 60


def test_special_arrangement_does_not_finalize_overtime_category():
    day = build_timekeeping_report([_row(overtime_minutes=90, work_arrangement=True)])["days"][0]
    assert day["overtime_40"] == 0
    assert any("Ειδικό καθεστώς" in warning for warning in day["warnings"])
