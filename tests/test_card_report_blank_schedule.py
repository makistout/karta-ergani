"""Blank schedule must not become needs_checkin / «Αναμένεται είσοδος»."""

from app.card_report import _evaluate_row, _schedule_shows_blank


def test_schedule_shows_blank_for_empty_hours():
    assert _schedule_shows_blank(None) is True
    assert _schedule_shows_blank({}) is True
    assert _schedule_shows_blank({"hour_from": "", "hour_to": "", "shift_type": ""}) is True
    assert _schedule_shows_blank({"hour_from": "09:00", "hour_to": "17:00"}) is False
    assert _schedule_shows_blank({"shift_type": "ΑΝΑΠΑΥΣΗ"}) is False


def test_blank_schedule_without_work_is_no_schedule():
    ev = _evaluate_row(
        sched={"hour_from": "", "hour_to": "", "shift_type": "", "eponymo": "TEST"},
        wl=None,
        card_in=None,
        card_out=None,
        work_date_ergani="03/08/2026",
    )
    assert ev["status"] == "no_schedule"
    assert ev["status_label"] == "Χωρίς εγγραφή ωραρίου"
    assert ev["status"] != "needs_checkin"


def test_blank_schedule_with_card_in_is_unscheduled_work():
    ev = _evaluate_row(
        sched={"hour_from": None, "hour_to": None, "shift_type": None},
        wl=None,
        card_in={"f_date": "03/08/2026 09:00", "f_type": "0"},
        card_out=None,
        work_date_ergani="03/08/2026",
    )
    assert ev["status"] == "unscheduled_work"


def test_rest_day_with_arrival_signal_is_shown_as_at_work():
    ev = _evaluate_row(
        sched={"hour_from": "", "hour_to": "", "shift_type": "ΑΝΑΠΑΥΣΗ"},
        wl={"hour_from": "09:04", "hour_to": ""},
        card_in=None,
        card_out=None,
        work_date_ergani="03/09/2026",
    )
    assert ev["status"] == "at_work"
    assert ev["status_label"] == "Σε εργασία"
    assert "δήλωση αποχώρησης" in ev["action"]
