from datetime import date

from app.apologistic import build_weekly_report, previous_week


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


def test_flexible_arrival_needs_no_change():
    result = build_weekly_report([sched()], [punch()], [contract()])
    assert result["days"][0]["status"] == "ok"
    assert result["days"][0]["employee_afm"] == "012345678"
    assert result["counts"]["ok"] == 1


def test_punch_without_schedule_is_review_not_automatic_work():
    result = build_weekly_report([], [punch()], [contract()])
    row = result["days"][0]
    assert row["status"] == "review"
    assert row["proposed"] == "09:10–17:10"


def test_schedule_without_punch_is_review():
    result = build_weekly_report([sched()], [], [contract()])
    assert result["days"][0]["status"] == "review"


def test_best_punch_is_closest_to_declared_schedule():
    result = build_weekly_report(
        [sched()], [punch("05:00", "06:00"), punch("09:02", "17:03")], [contract()]
    )
    row = result["days"][0]
    assert row["actual"] == "09:02–17:03"
    assert row["orphan_punch_count"] == 1
    assert row["status"] == "review"


def test_late_shift_proposes_same_declared_duration():
    result = build_weekly_report([sched()], [punch("10:00", "18:30")], [contract()])
    row = result["days"][0]
    assert row["status"] == "change"
    assert row["proposed"] == "10:00–18:00"
    assert row["extra_minutes"] == 30
    assert row["start_difference_minutes"] == 60
    assert row["end_difference_minutes"] == 90
    assert row["gross_difference_minutes"] == 30


def test_rest_with_punch_requires_review():
    result = build_weekly_report(
        [sched(start=None, end=None, shift="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")], [punch()], [contract()]
    )
    assert result["days"][0]["status"] == "review"


def test_outside_break_only_reduces_difference_on_work_day_with_punch():
    result = build_weekly_report(
        [sched()], [punch("09:00", "18:00")],
        [contract(flex=0, break_minutes=30, break_in_work=0)],
    )
    row = result["days"][0]
    assert row["gross_difference_minutes"] == 60
    assert row["outside_break_minutes"] == 30
    assert row["net_difference_minutes"] == 30


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


def test_missing_exit_is_completed_from_declared_boundary():
    result = build_weekly_report([sched()], [punch("09:00", None)], [contract(flex=0)])
    row = result["days"][0]
    assert row["actual"] == "09:00–17:00"
    assert row["punch_completeness"] == "Τεκμαρτό"
    assert row["status"] == "ok"


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
