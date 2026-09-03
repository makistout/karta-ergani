from datetime import date

from app.apologistic import (
    build_weekly_report, previous_week, _contract_for_day, _is_catering_contract,
)


def sched(afm="012345678", day="03/08/2026", start="09:00", end="17:00", shift="ΕΡΓΑΣΙΑ",
          break_minutes=None, break_in_work=None):
    return {"employee_afm": afm, "work_date": day, "hour_from": start,
            "hour_to": end, "shift_type": shift, "eponymo": "ΔΟΚΙΜΗ", "onoma": "Α",
            "break_minutes": break_minutes, "break_in_work": break_in_work}


def punch(start="09:10", end="17:10", afm="012345678", day="03/08/2026"):
    return {"employee_afm": afm, "work_date": day, "hour_from": start,
            "hour_to": end, "eponymo": "ΔΟΚΙΜΗ", "onoma": "Α"}


def contract(afm="012345678", flex=15, days="5", break_minutes=None, break_in_work=None):
    return {"employee_afm": afm, "characterization": "ΠΛΗΡΗΣ ΑΠΑΣΧΟΛΗΣΗ",
            "weekly_work_days": days, "flex_arrival_minutes": flex,
            "break_minutes": break_minutes, "break_in_work": break_in_work}


def test_previous_complete_week():
    assert previous_week(date(2026, 8, 9)) == (date(2026, 7, 27), date(2026, 8, 2))


def test_contract_is_selected_by_the_date_on_which_it_applies():
    contracts = [
        {"characterization": "Πλήρης", "effective_from": "01/08/2026"},
        {"characterization": "Μερική", "effective_from": "20/08/2026"},
    ]
    assert _contract_for_day(contracts, "19/08/2026")["characterization"] == "Πλήρης"
    assert _contract_for_day(contracts, "20/08/2026")["characterization"] == "Μερική"


def test_catering_is_detected_from_contract_and_can_be_overridden():
    assert _is_catering_contract({"specialty": "Υπάλληλος επισιτιστικών"}) is True
    assert _is_catering_contract({"specialty": "Μάγειρας", "catering_override": True}) is True
    assert _is_catering_contract({"specialty": "Επισιτιστικά", "catering_override": False}) is False


def test_flexible_arrival_needs_no_change():
    result = build_weekly_report([sched()], [punch()], [contract()])
    assert result["days"][0]["status"] == "ok"
    assert result["days"][0]["employee_afm"] == "012345678"
    assert result["counts"]["ok"] == 1


def test_punch_without_schedule_is_rest_to_work_change():
    result = build_weekly_report([], [punch()], [contract()])
    row = result["days"][0]
    assert row["status"] == "change"
    assert row["proposed"] == "09:10–17:10"
    assert row["rule_id"] == "NON_WORK_DAY_BECOMES_WORK"


def test_schedule_without_punch_is_ok_and_does_not_infer_actual_work():
    result = build_weekly_report([sched()], [], [contract()])
    row = result["days"][0]
    assert row["status"] == "ok"
    assert row["actual_minutes"] is None
    assert row["overtime_minutes"] == 0
    assert row["requires_confirmation"] is False


def test_declared_leave_without_punch_is_omitted_from_report():
    result = build_weekly_report(
        [sched(start=None, end=None, shift="Κανονική άδεια")],
        [],
        [contract()],
    )

    assert result["days"] == []
    assert result["counts"] == {"all": 0, "ok": 0, "change": 0, "review": 0}


def test_exact_eight_hour_declaration_changes_daily_basis_not_six_day_contract():
    schedules, punches = [], []
    for index in range(5):
        day = f"{3 + index:02d}/08/2026"
        schedules.append(sched(day=day, start="09:00", end="17:00"))
        punches.append(punch(day=day, start="09:00", end="17:00"))
    punches[-1] = punch(day="07/08/2026", start="09:00", end="17:30")

    rows = build_weekly_report(schedules, punches, [contract(flex=0, days="6")])["days"]
    friday = next(row for row in rows if row["work_date"] == "07/08/2026")
    assert friday["weekly_days"] == 6
    assert friday["weekly_days_source"] == "Σύμβαση εργαζομένου"
    assert friday["daily_overtime_basis_days"] == 5
    assert friday["daily_overtime_basis_source"] == "Δηλωμένο ωράριο ημέρας ακριβώς 8:00"
    assert friday["overwork_minutes"] == 30
    assert friday["overtime_minutes"] == 0


def test_exact_six_forty_declaration_changes_daily_basis_not_five_day_contract():
    schedules, punches = [], []
    for index in range(6):
        day = f"{3 + index:02d}/08/2026"
        schedules.append(sched(day=day, start="08:00", end="14:40"))
        punches.append(punch(day=day, start="08:00", end="14:40"))
    punches[-1] = punch(day="08/08/2026", start="08:00", end="16:30")

    rows = build_weekly_report(schedules, punches, [contract(flex=0, days="5")])["days"]
    saturday = next(row for row in rows if row["work_date"] == "08/08/2026")
    assert saturday["weekly_days"] == 5
    assert saturday["weekly_days_source"] == "Σύμβαση εργαζομένου"
    assert saturday["daily_overtime_basis_days"] == 6
    assert saturday["daily_overtime_basis_source"] == "Δηλωμένο ωράριο ημέρας ακριβώς 6:40"
    assert saturday["overwork_minutes"] == 80
    assert saturday["overtime_minutes"] == 30


def test_non_standard_declared_duration_falls_back_to_contract():
    row = build_weekly_report(
        [sched(start="09:00", end="16:00")],
        [punch(start="09:00", end="18:00")],
        [contract(flex=0, days="5")],
    )["days"][0]
    assert row["weekly_days"] == 5
    assert row["weekly_days_source"] == "Σύμβαση εργαζομένου"
    assert row["daily_overtime_basis_days"] == 5
    assert row["daily_overtime_basis_source"] == "Σύμβαση εργαζομένου"


def test_mixed_exact_durations_fall_back_to_contract():
    schedules = [
        sched(day="03/08/2026", start="09:00", end="17:00"),
        sched(day="04/08/2026", start="09:00", end="15:40"),
    ]
    rows = build_weekly_report(schedules, [], [contract(flex=0, days="6")])["days"]
    assert {row["weekly_days"] for row in rows} == {6}
    assert {row["weekly_days_source"] for row in rows} == {"Σύμβαση εργαζομένου"}
    by_date = {row["work_date"]: row for row in rows}
    assert by_date["03/08/2026"]["daily_overtime_basis_days"] == 5
    assert by_date["04/08/2026"]["daily_overtime_basis_days"] == 6


def test_non_split_uses_longest_complete_interval():
    result = build_weekly_report(
        [sched()], [punch("09:15", "13:00"), punch("09:02", "17:03")], [contract()]
    )
    row = result["days"][0]
    assert row["actual"] == "09:02–17:03"
    assert row["actual_minutes"] == 481
    assert row["orphan_punch_count"] == 0


def test_late_shift_proposes_same_declared_duration():
    result = build_weekly_report([sched()], [punch("10:00", "18:30")], [contract()])
    row = result["days"][0]
    assert row["status"] == "change"
    assert row["proposed"] == "10:00–18:00"
    assert row["extra_minutes"] == 30
    assert row["start_difference_minutes"] == 60
    assert row["end_difference_minutes"] == 90
    assert row["gross_difference_minutes"] == 30


def test_rest_with_punch_becomes_work_change_when_no_exchange_exists():
    result = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")], [punch()], [contract()]
    )
    row = result["days"][0]
    assert row["status"] == "change"
    assert row["rule_id"] == "NON_WORK_DAY_BECOMES_WORK"
    assert row["weekly_punch_days"] == 1
    assert row["contract_required_days"] == 5


def test_punch_without_any_declared_schedule_is_treated_as_rest():
    result = build_weekly_report([], [punch()], [contract()])
    row = result["days"][0]
    assert row["day_state"] == "Ρεπό"
    assert row["declared"] == "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
    assert row["status"] == "change"
    assert row["rule_id"] == "NON_WORK_DAY_BECOMES_WORK"


def test_next_day_punch_within_carry_window_extends_previous_day():
    schedules = [
        sched(day="15/08/2026", start="17:30", end="01:30"),
        sched(day="16/08/2026", start="17:30", end="01:30"),
    ]
    previous = punch(day="15/08/2026", start="17:19", end="01:15")
    previous["is_end_date_different"] = 1
    covered_by_previous = punch(day="16/08/2026", start="01:38", end="01:39")
    current = punch(day="16/08/2026", start="17:29", end="00:28")
    current["is_end_date_different"] = 1

    rows = build_weekly_report(
        schedules,
        [previous, covered_by_previous, current],
        [contract(flex=0)],
    )["days"]

    previous_row = next(row for row in rows if row["work_date"] == "15/08/2026")
    current_row = next(row for row in rows if row["work_date"] == "16/08/2026")
    assert current_row["punch_recorded"] == "17:29–00:28*"
    assert current_row["actual"] == "17:29–00:28"
    assert current_row["actual_minutes"] == 419
    assert current_row["punch_count"] == 1
    assert current_row["excluded_by_previous_overnight"] == [
        {"from": "01:38", "to": "01:39", "label": "01:38–01:39"}
    ]
    assert previous_row["carried_overnight_punches"] == [
        {"from": "01:38", "to": "01:39", "label": "01:38–01:39"}
    ]
    assert previous_row["actual"] == "17:19–01:39"


def test_pissakis_continuation_updates_previous_and_leaves_main_shift_on_new_day():
    schedules = [
        sched(day="15/08/2026", start="16:00", end="00:00"),
        sched(day="16/08/2026", start="16:00", end="00:00"),
    ]
    previous = punch(day="15/08/2026", start="15:26", end="00:24")
    previous["is_end_date_different"] = 1
    continuation = punch(day="16/08/2026", start="00:55", end="01:00")
    main_shift = punch(day="16/08/2026", start="16:46", end="23:58")

    rows = build_weekly_report(
        schedules, [previous, continuation, main_shift], [contract(flex=0)]
    )["days"]
    previous_row = next(row for row in rows if row["work_date"] == "15/08/2026")
    current_row = next(row for row in rows if row["work_date"] == "16/08/2026")

    assert previous_row["actual"] == "15:26–01:00"
    assert previous_row["actual_minutes"] == 574
    assert previous_row["carried_overnight_punches"] == [
        {"from": "00:55", "to": "01:00", "label": "00:55–01:00"}
    ]
    assert current_row["punch_recorded"] == "16:46–23:58"
    assert current_row["actual"] == "16:46–23:58"
    assert current_row["punch_count"] == 1
    assert current_row["proposed"] == "16:46–00:46"
    assert current_row["rule_id"] != "POSSIBLE_SPLIT_REVIEW"


def test_two_complete_pairs_with_three_hour_gap_are_possible_split_review():
    row = build_weekly_report(
        [sched(start="09:00", end="17:00")],
        [punch("09:00", "12:00"), punch("15:00", "20:00")],
        [contract(flex=0)],
    )["days"][0]

    assert row["status"] == "review"
    assert row["rule_id"] == "POSSIBLE_SPLIT_REVIEW"
    assert row["reason"] == "ΠΙΘΑΝΟ ΣΠΑΣΤΟ ΩΡΑΡΙΟ"
    assert row["actual"] == "09:00–12:00 · 15:00–20:00"
    assert row["actual_minutes"] == 480
    assert row["proposed"] == "09:00–12:00 · 15:00–20:00"


def test_early_pair_and_starred_main_shift_are_possible_split_review():
    early = punch("00:08", "00:26", day="03/08/2026")
    main = punch("17:42", "00:35", day="03/08/2026")
    main["is_end_date_different"] = 1

    row = build_weekly_report(
        [sched(day="03/08/2026", start="17:00", end="01:00")],
        [early, main],
        [contract(flex=0)],
    )["days"][0]

    assert row["status"] == "review"
    assert row["rule_id"] == "POSSIBLE_SPLIT_REVIEW"
    assert row["reason"] == "ΠΙΘΑΝΟ ΣΠΑΣΤΟ ΩΡΑΡΙΟ"
    assert row["actual"] == "00:08–00:26 · 17:42–00:35"
    assert row["actual_minutes"] == 431
    assert row["proposed"] == "00:08–00:26 · 17:42–01:24"


def test_pair_after_thirteen_hour_carry_window_stays_on_new_day():
    schedules = [
        sched(day="15/08/2026", start="16:00", end="00:00"),
        sched(day="16/08/2026", start="16:00", end="00:00"),
    ]
    previous = punch(day="15/08/2026", start="15:26", end="00:24")
    previous["is_end_date_different"] = 1
    outside_window = punch(day="16/08/2026", start="04:30", end="04:35")
    main_shift = punch(day="16/08/2026", start="16:46", end="23:58")

    rows = build_weekly_report(
        schedules, [previous, outside_window, main_shift], [contract(flex=0)]
    )["days"]
    previous_row = next(row for row in rows if row["work_date"] == "15/08/2026")
    current_row = next(row for row in rows if row["work_date"] == "16/08/2026")

    assert previous_row["actual"] == "15:26–00:24"
    assert previous_row["carried_overnight_punches"] == []
    assert current_row["rule_id"] == "POSSIBLE_SPLIT_REVIEW"
    assert current_row["reason"] == "ΠΙΘΑΝΟ ΣΠΑΣΤΟ ΩΡΑΡΙΟ"


def test_early_next_day_punch_carried_without_star_on_previous_day():
    """Overnight carry uses clock window only, not the ``*`` marker on the previous row."""
    schedules = [
        sched(day="05/06/2026", start="14:57", end="00:49"),
        sched(day="06/06/2026", start="14:57", end="00:49"),
        sched(day="07/06/2026", start="14:54", end="23:47"),
    ]
    day5 = punch(day="05/06/2026", start="14:57", end="23:55")
    day6_early = punch(day="06/06/2026", start="00:06", end="00:57")
    day6_main = punch(day="06/06/2026", start="14:57", end="23:55")
    day7_early = punch(day="07/06/2026", start="00:06", end="00:49")
    day7_main = punch(day="07/06/2026", start="14:54", end="23:47")

    rows = build_weekly_report(
        schedules,
        [day5, day6_early, day6_main, day7_early, day7_main],
        [contract(flex=0)],
    )["days"]
    row5 = next(row for row in rows if row["work_date"] == "05/06/2026")
    row6 = next(row for row in rows if row["work_date"] == "06/06/2026")
    row7 = next(row for row in rows if row["work_date"] == "07/06/2026")

    assert row5["actual"] == "14:57–00:57"
    assert row6["punch_recorded"] == "14:57–00:49*"
    assert row6["actual"] == "14:57–00:49"
    assert row6["rule_id"] != "POSSIBLE_SPLIT_REVIEW"
    assert row7["punch_recorded"] == "14:54–23:47"
    assert row7["rule_id"] != "POSSIBLE_SPLIT_REVIEW"


def test_pair_after_starred_end_but_before_thirteen_hour_limit_is_carried():
    schedules = [
        sched(day="15/08/2026", start="16:00", end="00:00"),
        sched(day="16/08/2026", start="16:00", end="00:00"),
    ]
    previous = punch(day="15/08/2026", start="15:26", end="00:24")
    previous["is_end_date_different"] = 1
    continuation = punch(day="16/08/2026", start="02:25", end="02:30")
    main_shift = punch(day="16/08/2026", start="16:46", end="23:58")

    rows = build_weekly_report(
        schedules, [previous, continuation, main_shift], [contract(flex=0)]
    )["days"]
    previous_row = next(row for row in rows if row["work_date"] == "15/08/2026")
    current_row = next(row for row in rows if row["work_date"] == "16/08/2026")

    assert previous_row["actual"] == "15:26–02:30"
    assert previous_row["carried_overnight_punches"] == [
        {"from": "02:25", "to": "02:30", "label": "02:25–02:30"}
    ]
    assert current_row["punch_recorded"] == "16:46–23:58"
    assert current_row["rule_id"] != "POSSIBLE_SPLIT_REVIEW"


def test_rest_punch_becomes_change_when_no_missing_declared_day_exists():
    schedules, punches = [], []
    for offset in range(5):
        day = f"{3 + offset:02d}/08/2026"
        if offset == 4:
            schedules.append(sched(day=day, start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"))
        else:
            schedules.append(sched(day=day))
        punches.append(punch(day=day))
    row = next(item for item in build_weekly_report(schedules, punches, [contract(days="5")])["days"]
               if item["work_date"] == "07/08/2026")
    assert row["status"] == "change"
    assert row["rule_id"] == "NON_WORK_DAY_BECOMES_WORK"
    assert row["weekly_punch_days"] == 5
    assert row["contract_required_days"] == 5
    assert row["replacement_candidates"] == []
    assert [item["work_date"] for item in row["weekly_punch_details"]] == [
        "03/08/2026", "04/08/2026", "05/08/2026", "06/08/2026", "07/08/2026"
    ]
    assert row["weekly_punch_details"][0]["punches"] == ["09:10–17:10"]
    assert any("03/08/2026: 09:10–17:10" in line for line in row["status_explanation"])


def test_non_work_to_work_full_short_punch_keeps_punch_duration():
    schedules = [
        sched(day="03/08/2026"),
        sched(day="04/08/2026", start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"),
    ]
    punches = [
        punch(day="03/08/2026", start="09:00", end="17:00"),
        punch(day="04/08/2026", start="10:00", end="14:00"),
    ]
    row = next(item for item in build_weekly_report(
        schedules, punches, [contract(flex=0, days="5")]
    )["days"] if item["work_date"] == "04/08/2026")
    assert row["proposed"] == "10:00–14:00"
    assert row["non_work_to_work_duration_rule"] == "PUNCH_DURATION_BELOW_CONTRACT_BASE"


def test_non_work_to_work_full_long_punch_uses_contract_base_and_extra_bands():
    schedules = [
        sched(day="03/08/2026"),
        sched(day="04/08/2026", start=None, end=None, shift="ΜΗ ΕΡΓΑΣΙΑ"),
    ]
    punches = [
        punch(day="03/08/2026", start="09:00", end="17:00"),
        punch(day="04/08/2026", start="09:00", end="19:00"),
    ]
    row = next(item for item in build_weekly_report(
        schedules, punches, [contract(flex=0, days="5")]
    )["days"] if item["work_date"] == "04/08/2026")
    assert row["proposed"] == "09:00–17:00"
    assert row["overwork_minutes"] == 60
    assert row["overtime_minutes"] == 60
    assert row["non_work_to_work_duration_rule"] == "CONTRACT_BASE_WITH_EXTRA_CLASSIFICATION"


def test_non_work_to_work_rotating_long_punch_uses_contract_base_without_overwork():
    rotating = contract(flex=0, days="5")
    rotating["characterization"] = "ΕΚ ΠΕΡΙΤΡΟΠΗΣ ΑΠΑΣΧΟΛΗΣΗ"
    row = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")],
        [punch(start="09:00", end="18:00")],
        [rotating],
    )["days"][0]
    assert row["proposed"] == "09:00–17:00"
    assert row["overwork_minutes"] == 0
    assert row["overtime_minutes"] == 60
    assert row["non_work_to_work_duration_rule"] == "CONTRACT_BASE_WITH_EXTRA_CLASSIFICATION"


def test_non_work_to_work_partial_uses_punch_duration_with_full_day_cap():
    partial = contract(flex=0, days="6")
    partial["characterization"] = "ΜΕΡΙΚΗ ΑΠΑΣΧΟΛΗΣΗ"
    partial["weekly_hours"] = 20
    row = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")],
        [punch(start="09:00", end="18:00")],
        [partial],
    )["days"][0]
    assert row["proposed"] == "09:00–15:40"
    assert row["overtime_minutes"] == 0
    assert row["non_work_to_work_duration_rule"] == "PARTIAL_PUNCH_DURATION_CAPPED_AT_FULL_DAY"


def test_five_day_rest_punch_with_missing_declared_day_requires_exchange_review():
    schedules = [
        sched(day="03/08/2026", start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"),
        sched(day="04/08/2026"),
        sched(day="05/08/2026"),
        sched(day="06/08/2026"),
        sched(day="07/08/2026"),
        sched(day="08/08/2026", start="17:30", end="01:30"),
        sched(day="09/08/2026", start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"),
    ]
    punches = [
        punch(day="03/08/2026", start="13:05", end="20:20"),
        punch(day="04/08/2026"),
        punch(day="05/08/2026"),
        punch(day="06/08/2026"),
        punch(day="07/08/2026"),
        punch(day="09/08/2026", start="17:23", end="00:55"),
    ]

    rest_rows = [
        row for row in build_weekly_report(schedules, punches, [contract(days="5")])["days"]
        if row["work_date"] in ("03/08/2026", "09/08/2026")
    ]
    assert len(rest_rows) == 2
    review_rows = [row for row in rest_rows if row["status"] == "review"]
    assert len(review_rows) == 1
    assert review_rows[0]["weekly_punch_days"] == 6
    assert review_rows[0]["contract_required_days"] == 5
    assert [item["work_date"] for item in review_rows[0]["replacement_candidates"]] == ["08/08/2026"]
    assert review_rows[0]["exchange_options"][0]["replacement_work_date"] == "08/08/2026"
    assert review_rows[0]["exchange_options"][0]["replacement_proposed"] == "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
    assert review_rows[0]["exchange_options"][0]["contract_duration_minutes"] == 480
    assert "επιλογή ανταλλαγής" in review_rows[0]["reason"]
    assert len([row for row in rest_rows if row["rule_id"] == "NON_WORK_DAY_BECOMES_WORK"]) == 1


def test_sunday_sixth_day_over_five_hours_creates_next_week_rest_due():
    schedules, punches = [], []
    for offset in range(6):
        day = f"{3 + offset:02d}/08/2026" if offset < 5 else "09/08/2026"
        schedules.append(sched(day=day, start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ") if offset == 5 else sched(day=day))
        punches.append(punch(day=day, start="09:00", end="15:01"))
    sunday = next(row for row in build_weekly_report(
        schedules, punches, [contract(days="5")], sunday_rest_transfer_enabled=True,
    )["days"] if row["work_date"] == "09/08/2026")
    assert sunday["compensatory_rest_due"] is True
    assert sunday["compensatory_rest_target_week"] == "2026-08-10"
    assert sunday["proposed"] == "09:00–15:01"


def test_sunday_rest_transfer_disabled_by_default():
    schedules, punches = [], []
    for offset in range(6):
        day = f"{3 + offset:02d}/08/2026" if offset < 5 else "09/08/2026"
        schedules.append(sched(day=day, start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ") if offset == 5 else sched(day=day))
        punches.append(punch(day=day, start="09:00", end="15:01"))
    sunday = next(row for row in build_weekly_report(schedules, punches, [contract(days="5")])["days"]
                  if row["work_date"] == "09/08/2026")
    assert sunday["compensatory_rest_due"] is False
    assert sunday["compensatory_rest_target_week"] is None


def test_sunday_five_hours_does_not_create_next_week_rest_due():
    schedules, punches = [], []
    for offset in range(6):
        day = f"{3 + offset:02d}/08/2026" if offset < 5 else "09/08/2026"
        schedules.append(sched(day=day, start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ") if offset == 5 else sched(day=day))
        punches.append(punch(day=day, start="09:00", end="14:00"))
    sunday = next(row for row in build_weekly_report(
        schedules, punches, [contract(days="5")], sunday_rest_transfer_enabled=True,
    )["days"] if row["work_date"] == "09/08/2026")
    assert sunday["compensatory_rest_due"] is False


def test_rest_punch_requires_exchange_when_a_declared_workday_is_missing():
    schedules = [
        sched(day="03/08/2026"),
        sched(day="04/08/2026"),
        sched(day="05/08/2026", start=None, end=None, shift="ΜΗ ΕΡΓΑΣΙΑ"),
    ]
    punches = [punch(day="03/08/2026"), punch(day="05/08/2026")]
    row = next(item for item in build_weekly_report(schedules, punches, [contract(days="5")])["days"]
               if item["work_date"] == "05/08/2026")
    assert row["status"] == "review"
    assert row["weekly_punch_days"] == 2
    assert row["contract_required_days"] == 5
    assert [item["work_date"] for item in row["replacement_candidates"]] == ["04/08/2026"]
    assert row["rule_id"] == "REST_WORK_EXCHANGE_REVIEW"
    assert row["exchange_options"][0]["replacement_proposed"] == "ΜΗ ΕΡΓΑΣΙΑ"


def test_full_five_day_work_on_rest_becomes_change():
    row = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")],
        [punch("07:57", "16:58")],
        [contract(flex=0, days="5")],
    )["days"][0]
    assert row["status"] == "change"
    assert row["weekly_punch_days"] == 1
    assert row["proposed"] == "07:57–15:57"
    assert row["actual_minutes"] == 541
    assert row["overwork_minutes"] == 60
    assert row["overtime_minutes"] == 1
    assert row["overtime_segments"] == [
        {"date": "03/08/2026", "from": "16:57", "to": "16:58", "minutes": 1}
    ]


def test_full_six_day_work_on_rest_becomes_change():
    row = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")],
        [punch("08:00", "16:01")],
        [contract(flex=0, days="6")],
    )["days"][0]
    assert row["status"] == "change"
    assert row["weekly_punch_days"] == 1
    assert row["proposed"] == "08:00–14:40"
    assert row["overwork_minutes"] == 80
    assert row["overtime_minutes"] == 1


def test_outside_break_only_reduces_difference_on_work_day_with_punch():
    result = build_weekly_report(
        [sched()], [punch("09:00", "18:00")],
        [contract(flex=0, break_minutes=30, break_in_work=0)],
    )
    row = result["days"][0]
    assert row["gross_difference_minutes"] == 60
    assert row["outside_break_minutes"] == 30
    assert row["net_difference_minutes"] == 30


def test_outside_break_is_not_added_to_schedule_proposal():
    row = build_weekly_report(
        [sched(day="08/08/2026", start="10:00", end="17:00")],
        [punch("09:57", "15:59", day="08/08/2026")],
        [contract(flex=15, break_minutes=30, break_in_work=0)],
    )["days"][0]
    assert row["outside_break_minutes"] == 30
    assert row["proposed"] == "09:57–16:57"
    assert row["status"] == "change"


def test_outside_break_extends_overtime_threshold_not_proposal():
    row = build_weekly_report(
        [sched(start="09:00", end="17:00")],
        [punch("09:00", "19:00")],
        [contract(flex=0, break_minutes=30, break_in_work=0, days="5")],
    )["days"][0]
    assert row["proposed"] == "09:00–17:00"
    assert row["overtime_from"] == "18:30"


def test_break_not_subtracted_on_rest_without_punch():
    result = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")], [],
        [contract(break_minutes=30, break_in_work=0)],
    )
    row = result["days"][0]
    assert row["outside_break_minutes"] == 0
    assert row["net_difference_minutes"] is None


def test_night_minutes_are_visible():
    result = build_weekly_report(
        [sched(start="22:00", end="06:00")], [punch("22:00", "06:00")], [contract()]
    )
    assert result["days"][0]["night_minutes"] == 480


def test_sixth_actual_day_is_not_automatically_changed_by_retrospective_engine():
    schedules, punches = [], []
    for index in range(6):
        day = f"{3 + index:02d}/08/2026"
        schedules.append(sched(day=day))
        punches.append(punch(day=day))
    result = build_weekly_report(schedules, punches, [contract(days="5")])
    assert not any(row["sixth_day_candidate"] for row in result["days"])


def test_missing_exit_uses_declared_exit_and_is_compliant():
    result = build_weekly_report([sched()], [punch("09:00", None)], [contract(flex=0)])
    row = result["days"][0]
    assert row["punch_recorded"] == "09:00–"
    assert row["actual"] == "09:00–17:00"
    assert row["punch_completeness"] == "Τεκμαρτό"
    assert row["status"] == "ok"
    assert row["rule_id"] == "FLEX_COMPLIANT"
    assert any("Λείπει έξοδος" in line for line in row["status_explanation"])


def test_missing_exit_early_start_does_not_create_overtime():
    row = build_weekly_report(
        [sched(start="13:00", end="21:00")],
        [punch("09:00", None)],
        [contract(flex=0, break_minutes=30, break_in_work=1)],
    )["days"][0]
    assert row["punch_recorded"] == "09:00–"
    assert row["actual"] == "09:00–17:00"
    assert row["proposed"] == "09:00–17:00"
    assert row["status"] == "change"
    assert row["rule_id"] == "EARLY_START_SHIFT"
    assert row["overtime_minutes"] == 0
    assert row["overwork_minutes"] == 0
    assert row["overtime_segments"] == []
    assert any("τεκμαρτή λήξη" in line and "17:00" in line for line in row["status_explanation"])


def test_missing_entry_with_extra_minutes_rebuilds_backwards_without_overtime():
    row = build_weekly_report(
        [sched(start="13:00", end="21:00")],
        [punch(None, "21:05")],
        [contract(flex=0, break_minutes=30, break_in_work=1)],
    )["days"][0]
    assert row["punch_recorded"] == "–21:05"
    assert row["actual"] == "13:00–21:05"
    assert row["proposed"] == "13:05–21:05"
    assert row["status"] == "change"
    assert row["rule_id"] == "MISSING_ENTRY_EXTRA_BACKWARD"
    assert row["overtime_minutes"] == 0
    assert row["overtime_segments"] == []


def test_missing_exit_with_outside_break_extends_physical_exit_only():
    row = build_weekly_report(
        [sched(start="15:00", end="23:00")],
        [punch("15:00", None)],
        [contract(flex=0, break_minutes=30, break_in_work=0)],
    )["days"][0]
    assert row["actual"] == "15:00–23:30"
    assert row["actual_minutes"] == 510
    assert row["effective_actual_minutes"] == 480
    assert row["proposed"] == "15:00–23:00"
    assert row["status"] == "ok"


def test_missing_entry_with_extra_hours_is_rebuilt_backwards_from_exit():
    row = build_weekly_report(
        [sched(start="15:00", end="23:00")],
        [punch(None, "00:00")],
        [contract(flex=0)],
    )["days"][0]
    assert row["actual"] == "15:00–00:00"
    assert row["proposed"] == "16:00–00:00"
    assert row["status"] == "change"
    assert row["rule_id"] == "MISSING_ENTRY_EXTRA_BACKWARD"


def test_missing_entry_without_extra_hours_uses_declared_start_and_is_compliant():
    row = build_weekly_report(
        [sched(start="15:00", end="23:00")],
        [punch(None, "23:00")],
        [contract(flex=0)],
    )["days"][0]
    assert row["actual"] == "15:00–23:00"
    assert row["proposed"] == "15:00–23:00"
    assert row["status"] == "ok"


def test_multiple_complete_non_split_punches_use_full_envelope():
    result = build_weekly_report(
        [sched()], [punch("09:02", "17:03"), punch("19:23", "20:30")], [contract()]
    )
    row = result["days"][0]
    assert row["punch_recorded"] == "09:02–17:03\n19:23–20:30"
    assert row["actual"] == "09:02–20:30"
    assert row["orphan_punch_count"] == 0
    assert any("μεγαλύτερο έγκυρο πραγματικό διάστημα" in line for line in row["status_explanation"])


def test_second_open_without_close_becomes_final_close_for_full_envelope():
    row = build_weekly_report(
        [sched()], [punch("09:00", "17:00"), punch("17:05", None)], [contract(flex=0)]
    )["days"][0]
    assert row["actual"] == "09:00–17:05"
    assert row["actual_minutes"] == 485
    assert row["corrected_extra_punches"] == [{"from": "17:05", "to": "17:05", "corrected": "17:05–17:05"}]
    assert any("Λανθασμένο πρόσθετο χτύπημα" in line for line in row["status_explanation"])


def test_erato_six_day_example_produces_overtime_proposal():
    row = build_weekly_report(
        [sched(start="12:00", end="18:40")],
        [punch("12:01", "18:41"), punch("19:23", "20:30")],
        [contract(flex=120, days="6", break_minutes=30, break_in_work=1)],
    )["days"][0]
    assert row["actual"] == "12:01–20:30"
    assert row["actual_minutes"] == 509
    assert row["overwork_minutes"] == 80
    assert row["overtime_minutes"] == 29
    assert row["overtime_segments"] == [
        {"date": "03/08/2026", "from": "20:01", "to": "20:30", "minutes": 29}
    ]


def test_rest_missing_exit_builds_reviewable_contract_duration():
    row = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")], [punch("12:30", None)], [contract()]
    )["days"][0]
    assert row["actual"] == "12:30–12:30"
    assert row["actual_minutes"] == 0
    assert row["status"] == "change"
    assert row["proposed"] == "12:30–20:30"
    assert row["weekly_punch_days"] == 1
    assert row["contract_required_days"] == 5


def test_rest_missing_exit_uses_exchange_when_declared_workday_has_no_punch():
    schedules = [
        sched(day="03/08/2026", start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"),
        sched(day="04/08/2026", start="09:00", end="17:00"),
    ]
    row = next(
        item for item in build_weekly_report(
            schedules, [punch("12:30", None, day="03/08/2026")], [contract(days="5")]
        )["days"]
        if item["work_date"] == "03/08/2026"
    )
    assert row["status"] == "review"
    assert row["rule_id"] == "REST_WORK_EXCHANGE_REVIEW"
    assert row["proposed"] == "12:30–20:30"
    assert [item["work_date"] for item in row["replacement_candidates"]] == ["04/08/2026"]


def test_rest_missing_entry_opens_at_exit_time():
    row = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")], [punch(None, "12:30")], [contract()]
    )["days"][0]
    assert row["actual"] == "12:30–12:30"
    assert row["actual_minutes"] == 0


def test_overtime_is_assigned_to_calendar_day_when_it_occurs():
    row = build_weekly_report(
        [sched(start="16:00", end="00:00")], [punch("16:00", "03:00")], [contract(flex=0)]
    )["days"][0]
    assert row["overtime_minutes"] == 120
    assert row["overtime_segments"] == [
        {"date": "04/08/2026", "from": "01:00", "to": "03:00", "minutes": 120}
    ]


def test_split_schedule_matches_each_punch_independently():
    schedules = [sched(start="09:00", end="13:00"), sched(start="17:00", end="21:00")]
    punches = [punch("17:05", "21:05"), punch("09:05", "13:05")]
    row = build_weekly_report(schedules, punches, [contract(flex=0)])["days"][0]
    assert row["actual"] == "09:05–13:05 · 17:05–21:05"
    assert row["matched_parts"] == 2
    assert row["orphan_punch_count"] == 0


def test_flexible_arrival_keeps_normal_schedule_and_declares_only_overtime():
    result = build_weekly_report(
        [sched()], [punch("09:30", "21:30")],
        [contract(flex=90, break_minutes=30, break_in_work=0)],
    )
    row = result["days"][0]
    assert row["status"] == "change"
    assert row["proposed"] == "09:00–17:00"
    assert row["overwork_minutes"] == 60
    assert row["overtime_minutes"] == 150
    assert (row["overtime_from"], row["overtime_to"]) == ("19:00", "21:30")


def test_full_six_day_daily_bands():
    row = build_weekly_report(
        [sched(start="08:00", end="14:40")], [punch("08:00", "18:00")],
        [contract(flex=0, days="6")],
    )["days"][0]
    assert row["overwork_minutes"] == 80
    assert row["overtime_minutes"] == 120


def test_partial_employment_does_not_generate_overtime_declaration():
    partial = contract(flex=0)
    partial["characterization"] = "ΜΕΡΙΚΗ ΑΠΑΣΧΟΛΗΣΗ"
    row = build_weekly_report(
        [sched(start="09:00", end="13:00")], [punch("09:00", "15:00")], [partial]
    )["days"][0]
    assert row["overtime_minutes"] == 0
    assert row["undeclared_extra_minutes"] == 120


def test_seven_declared_days_missing_card_proposes_rest_with_approval():
    schedules, punches = [], []
    for index in range(7):
        day = f"{3 + index:02d}/08/2026"
        schedules.append(sched(day=day))
        if index != 4:
            punches.append(punch(day=day))
    rows = build_weekly_report(schedules, punches, [contract()])["days"]
    missing = next(row for row in rows if row["punch_count"] == 0)
    assert missing["proposed"] == "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
    assert missing["suggested_rest"] is True
    assert missing["requires_confirmation"] is True


def test_blank_break_position_is_not_silently_subtracted():
    row = build_weekly_report(
        [sched()], [punch("09:00", "18:00")],
        [contract(flex=0, break_minutes=30, break_in_work=None)],
    )["days"][0]
    assert row["outside_break_minutes"] == 0
    assert row["requires_confirmation"] is True


def test_late_short_shift_is_proposed_backwards_from_exit():
    row = build_weekly_report(
        [sched()], [punch("14:00", "22:00")], [contract(flex=60)]
    )["days"][0]
    assert row["proposed"] == "14:00–22:00"
    assert row["proposal_basis"] == "Ανάστροφα από την πραγματική λήξη"
