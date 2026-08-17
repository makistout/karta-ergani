import pytest

from app.apologistic_submit import (
    overtime_segments_from_row,
    overtime_submit_group_from_row,
    parse_proposed_schedule,
    schedule_body_from_apologistic_row,
)
from app.wto_ov_payload import build_wto_ov_a_payload
from app.work_card_payload import WorkCardPayloadError


def _analytics(payload):
    return payload["WTOS"]["WTO"][0]["Ergazomenoi"]["ErgazomenoiWTO"][0][
        "ErgazomenosAnalytics"
    ]["ErgazomenosWTOAnalytics"]


def test_wto_ov_a_payload_uses_overtime_type():
    payload = build_wto_ov_a_payload(
        branch_aa="0",
        employee_afm="123456789",
        employee_last_name="ΠΑΠΑΔΟΠΟΥΛΟΣ",
        employee_first_name="ΝΙΚΟΣ",
        reference_date="2026-07-28",
        hour_from="21:00",
        hour_to="23:00",
    )
    assert _analytics(payload) == [
        {"f_type": "ΥΠ", "f_from": "21:00", "f_to": "23:00"},
    ]


def test_parse_proposed_schedule_rest_day():
    assert parse_proposed_schedule("ΑΝΑΠΑΥΣΗ/ΡΕΠΟ") == (None, None, "ΑΝ")


def test_parse_proposed_schedule_non_work():
    assert parse_proposed_schedule("ΜΗ ΕΡΓΑΣΙΑ") == (None, None, "ΜΕ")


def test_parse_proposed_schedule_telework():
    assert parse_proposed_schedule("ΤΗΛΕΡΓΑΣΙΑ 09:00–17:00") == ("09:00", "17:00", "ΤΗΛ")


def test_parse_proposed_schedule_work_range():
    assert parse_proposed_schedule("09:00–17:00") == ("09:00", "17:00", "ΕΡΓ")


def test_schedule_body_from_apologistic_row_change():
    row = {
        "status": "change",
        "proposed": "09:00–17:00",
        "employee_afm": "123456789",
        "eponymo": "ΠΑΠΑ",
        "onoma": "ΜΑΡΙΑ",
        "work_date": "28/07/2026",
    }
    body = schedule_body_from_apologistic_row(row)
    assert body["reference_date"] == "2026-07-28"
    assert body["hour_from"] == "09:00"
    assert body["schedule_type"] == "ΕΡΓ"


def test_schedule_body_preserves_telework_category_from_rule_engine():
    row = {
        "status": "change",
        "proposed": "09:00–17:00",
        "proposed_schedule_type": "ΤΗΛ",
        "employee_afm": "123456789",
        "eponymo": "ΠΑΠΑ",
        "onoma": "ΜΑΡΙΑ",
        "work_date": "28/07/2026",
    }
    assert schedule_body_from_apologistic_row(row)["schedule_type"] == "ΤΗΛ"


def test_schedule_body_supports_split_rule_engine_proposal():
    row = {
        "status": "change",
        "proposed": "09:00–13:00 · 16:00–20:00",
        "employee_afm": "123456789",
        "eponymo": "ΠΑΠΑ",
        "onoma": "ΜΑΡΙΑ",
        "work_date": "28/07/2026",
    }
    body = schedule_body_from_apologistic_row(row)
    assert body["intervals"] == [
        {"hour_from": "09:00", "hour_to": "13:00"},
        {"hour_from": "16:00", "hour_to": "20:00"},
    ]


def test_schedule_body_rejects_overtime_only_change():
    row = {
        "status": "change",
        "declared": "10:00–19:00",
        "proposed": "10:00–19:00",
        "overtime_from": "19:32",
        "overtime_to": "20:28",
        "overtime_minutes": 56,
        "employee_afm": "123456789",
        "work_date": "04/08/2026",
    }
    with pytest.raises(WorkCardPayloadError, match="μόνο απολογιστική υπερωρία"):
        schedule_body_from_apologistic_row(row)


def test_overtime_submit_group_requires_segment_date_for_multi_day():
    row = {
        "work_date": "28/07/2026",
        "overtime_segments": [
            {"date": "28/07/2026", "from": "22:00", "to": "24:00"},
            {"date": "29/07/2026", "from": "00:00", "to": "01:00"},
        ],
    }
    with pytest.raises(WorkCardPayloadError):
        overtime_submit_group_from_row(row)

    ref, segments = overtime_submit_group_from_row(row, segment_date_ergani="29/07/2026")
    assert ref == "2026-07-29"
    assert len(segments) == 1
    assert segments[0]["hour_from"] == "00:00"


def test_overtime_submit_group_rejects_review_status():
    row = {
        "status": "review",
        "work_date": "28/07/2026",
        "overtime_segments": [{"date": "28/07/2026", "from": "22:00", "to": "23:00"}],
    }
    with pytest.raises(WorkCardPayloadError, match="Έλεγχο"):
        overtime_submit_group_from_row(row)


def test_overtime_segments_from_row_fallback_fields():
    row = {
        "work_date": "28/07/2026",
        "overtime_from": "20:00",
        "overtime_to": "22:00",
    }
    segments = overtime_segments_from_row(row)
    assert segments[0]["reference_date"] == "2026-07-28"
