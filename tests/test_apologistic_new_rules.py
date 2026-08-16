from app.apologistic import build_weekly_report


def sched(day="03/08/2026", start="09:00", end="17:00", shift="ΕΡΓΑΣΙΑ"):
    return {"employee_afm": "012345678", "work_date": day, "hour_from": start,
            "hour_to": end, "shift_type": shift, "eponymo": "ΔΟΚΙΜΗ", "onoma": "Α"}


def punch(start="09:00", end="17:00", day="03/08/2026", **extra):
    value = {"employee_afm": "012345678", "work_date": day, "hour_from": start,
             "hour_to": end, "eponymo": "ΔΟΚΙΜΗ", "onoma": "Α"}
    value.update(extra)
    return value


def contract(kind="ΠΛΗΡΗΣ ΑΠΑΣΧΟΛΗΣΗ", days="5", flex=0, **extra):
    value = {"employee_afm": "012345678", "characterization": kind,
             "weekly_work_days": days, "flex_arrival_minutes": flex}
    value.update(extra)
    return value


def one(schedules, punches, agreement):
    return build_weekly_report(schedules, punches, [agreement])["days"][0]


def test_split_short_gap_is_rebuilt_with_three_hour_gap():
    row = one(
        [sched(start="09:00", end="13:00"), sched(start="16:00", end="20:00")],
        [punch("09:00", "14:00"), punch("16:00", "22:00")],
        contract(),
    )
    assert row["rule_id"] == "SPLIT_GAP_ADJUSTED"
    assert row["proposed"] == "09:00–13:00 · 16:00–20:00"


def test_split_overtime_starts_after_proposed_day_and_overwork_window():
    row = one(
        [sched(start="09:00", end="13:00"), sched(start="16:00", end="20:00")],
        [punch("09:00", "13:00"), punch("16:00", "22:00")],
        contract(days="5"),
    )
    assert row["proposed"] == "09:00–13:00 · 16:00–20:00"
    assert row["overtime_from"] == "21:00"
    assert row["overtime_to"] == "22:00"


def test_split_keeps_valid_first_part_and_builds_second_from_remainder():
    row = one(
        [sched(start="09:00", end="13:00"), sched(start="16:30", end="20:30")],
        [punch("09:00", "13:00"), punch("16:30", "22:00")],
        contract(),
    )
    assert row["rule_id"] == "SPLIT_REBUILT"
    assert row["proposed"] == "09:00–13:00 · 16:30–20:30"


def test_split_is_rejected_for_partial_employment():
    row = one(
        [sched(start="09:00", end="11:00"), sched(start="15:00", end="17:00")],
        [punch("09:00", "11:00"), punch("15:00", "17:00")],
        contract(kind="ΜΕΡΙΚΗ ΑΠΑΣΧΟΛΗΣΗ"),
    )
    assert row["status"] == "review"
    assert row["rule_id"] == "SPLIT_NON_FULL_REVIEW"


def test_partial_uses_actual_duration_with_five_day_cap_and_no_overtime():
    row = one([sched(start="09:00", end="13:00")], [punch("09:00", "19:00")],
              contract(kind="ΜΕΡΙΚΗ ΑΠΑΣΧΟΛΗΣΗ", days="5"))
    assert row["proposed"] == "09:00–17:00"
    assert row["rule_id"] == "PARTIAL_ACTUAL_CAPPED"
    assert row["overtime_minutes"] == 0


def test_partial_uses_six_day_cap():
    row = one([sched(start="09:00", end="12:00")], [punch("09:00", "18:00")],
              contract(kind="ΜΕΡΙΚΗ ΑΠΑΣΧΟΛΗΣΗ", days="6"))
    assert row["proposed"] == "09:00–15:40"
    assert row["overtime_minutes"] == 0


def test_rotating_overtime_uses_contract_base_not_shorter_declaration():
    row = one([sched(start="09:00", end="13:00")], [punch("09:00", "18:00")],
              contract(kind="ΕΚ ΠΕΡΙΤΡΟΠΗΣ ΑΠΑΣΧΟΛΗΣΗ", days="5"))
    assert row["overtime_minutes"] == 60
    assert row["overtime_from"] == "17:00"


def test_unpredictable_with_punch_uses_actual_capped_duration():
    row = one([sched()], [punch("10:00", "20:00")],
              contract(days="5", work_time_organization="ΜΗ ΠΡΟΒΛΕΨΙΜΟ"))
    assert row["rule_id"] == "UNPREDICTABLE_PUNCH"
    assert row["proposed"] == "10:00–18:00"


def test_unpredictable_without_punch_becomes_non_work():
    row = one([sched()], [], contract(work_time_organization="ΜΗ ΠΡΟΒΛΕΨΙΜΟ"))
    assert row["rule_id"] == "UNPREDICTABLE_NO_PUNCH"
    assert row["proposed"] == "ΜΗ ΕΡΓΑΣΙΑ"


def test_missing_exit_without_schedule_uses_contract_duration_and_review():
    row = one([], [punch("10:00", None)], contract(days="5"))
    assert row["status"] == "review"
    assert row["rule_id"] == "MISSING_EXIT_REBUILT"
    assert row["proposed"] == "10:00–18:00"


def test_late_arrival_is_still_compliant_when_exit_is_inside_flex_window():
    row = one([sched()], [punch("10:00", "17:10")], contract(flex=15))
    assert row["status"] == "ok"
    assert row["rule_id"] == "FLEX_COMPLIANT"


def test_daily_span_limit_for_five_day_contract_goes_to_review():
    row = one([sched()], [punch("06:00", "19:01")], contract(days="5"))
    assert row["status"] == "review"
    assert row["rule_id"] == "MAX_DAILY_SPAN_REVIEW"
    assert row["proposed"] == "06:00–14:00"
    assert "η πρόταση υπολογίστηκε" in row["reason"]


def test_rotating_exact_six_forty_uses_daily_six_day_basis_under_five_day_contract():
    row = one(
        [sched(start="09:00", end="15:40")],
        [punch("09:00", "18:00")],
        contract(kind="ΕΚ ΠΕΡΙΤΡΟΠΗΣ ΑΠΑΣΧΟΛΗΣΗ", days="5"),
    )
    assert row["weekly_days"] == 5
    assert row["daily_overtime_basis_days"] == 6
    assert row["overwork_minutes"] == 0
    assert row["overtime_minutes"] == 140
    assert row["overtime_from"] == "15:40"


def test_clock_wrap_within_daily_limit_is_treated_as_real_overnight():
    row = one([sched()], [punch("22:00", "06:00")], contract())
    assert row["actual"] == "22:00–06:00"
    assert row["actual_minutes"] == 480
    assert row["rule_id"] != "UNDECLARED_OVERNIGHT_REVIEW"


def test_explicit_next_day_exit_is_not_treated_as_reversed_punch_order():
    row = one(
        [sched(start="13:00", end="21:00")],
        [punch("17:26", "01:00", is_end_date_different=True)],
        contract(flex=120),
    )
    assert row["status"] == "change"
    assert row["rule_id"] == "LATE_SHORT_BACKWARD"
    assert row["proposed"] == "17:00–01:00"
    assert row["punch_recorded"] == "17:26–01:00*"


def test_multiple_punches_choose_longest_valid_real_span_for_general_checks_only():
    row = one(
        [sched(start="12:00", end="20:00")],
        [
            punch("12:01", "10:00"),  # 21:59: exceeds the five-day limit; invalid.
            punch("12:01", "20:30"),
            punch("21:00", "00:14", is_end_date_different=True),
        ],
        contract(days="5", flex=0),
    )
    assert row["punch_recorded"].endswith("21:00–00:14*")
    assert row["actual"] == "12:01–00:14"
    assert row["actual_minutes"] == 733
    assert row["overtime_worked_minutes"] == 1319
    assert row["overtime_minutes"] == 240
    assert row["overtime_segments"] == [
        {"date": "03/08/2026", "from": "21:01", "to": "01:01", "minutes": 240},
    ]


def test_reversed_exit_outside_daily_limit_does_not_participate_in_maximum_span():
    row = one(
        [sched(start="12:00", end="20:00")],
        [punch("12:01", "10:00"), punch("12:05", "20:30")],
        contract(days="5", flex=0),
    )
    assert row["actual"] == "12:01–20:30"
    assert row["actual_minutes"] == 509
    # The stricter pairing is a general validation rule only. Overtime keeps
    # the established outer-envelope calculation used before rules-v6.
    assert row["overtime_worked_minutes"] == 1319
    assert row["overtime_minutes"] == 240
    assert row["unlawful_overtime_minutes"] == 539


def test_overtime_submission_date_is_the_date_on_which_overtime_starts():
    common_schedule = [sched(day="18/08/2026", start="18:00", end="02:00")]
    common_contract = contract(days="5", flex=0, break_minutes=0, break_in_work=1)

    starts_next_day = one(
        common_schedule,
        [punch("18:00", "04:00", day="18/08/2026", is_end_date_different=True)],
        common_contract,
    )
    assert starts_next_day["overtime_segments"] == [
        {"date": "19/08/2026", "from": "03:00", "to": "04:00", "minutes": 60}
    ]

    starts_at_midnight = one(
        [sched(day="18/08/2026", start="15:00", end="23:00")],
        [punch("15:00", "01:00", day="18/08/2026", is_end_date_different=True)],
        common_contract,
    )
    assert starts_at_midnight["overtime_segments"] == [
        {"date": "19/08/2026", "from": "00:00", "to": "01:00", "minutes": 60}
    ]

    crosses_midnight = one(
        [sched(day="18/08/2026", start="14:00", end="22:00")],
        [punch("14:00", "01:00", day="18/08/2026", is_end_date_different=True)],
        common_contract,
    )
    assert crosses_midnight["overtime_segments"] == [
        {"date": "18/08/2026", "from": "23:00", "to": "01:00", "minutes": 120}
    ]


def test_telework_with_punch_keeps_category_and_applies_change():
    row = one([sched(start="09:00", end="17:00", shift="ΤΗΛΕΡΓΑΣΙΑ")],
              [punch("08:30", "16:30")], contract())
    assert row["day_state"] == "Τηλεργασία"
    assert row["status"] == "change"
    assert row["rule_id"] == "TELEWORK_WITH_PUNCH"
    assert row["proposed"] == "08:30–16:30"


def test_six_declared_days_for_five_day_contract_proposes_one_rest():
    schedules = []
    punches = []
    for offset in range(6):
        day = f"{3 + offset:02d}/08/2026"
        schedules.append(sched(day=day))
        if offset != 5:
            punches.append(punch(day=day))
    rows = build_weekly_report(schedules, punches, [contract(days="5")])["days"]
    rest = [row for row in rows if row["suggested_rest"]]
    assert len(rest) == 1
    assert rest[0]["proposed"] == "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
    assert rest[0]["rule_id"] == "SURPLUS_DECLARED_DAY_REST"
