import pytest

from app.wto_daily_payload import build_wto_daily_a_payload, build_wto_daily_payload
from app.work_card_payload import WorkCardPayloadError


def _analytics(payload):
    return payload["WTOS"]["WTO"][0]["Ergazomenoi"]["ErgazomenoiWTO"][0][
        "ErgazomenosAnalytics"
    ]["ErgazomenosWTOAnalytics"]


def test_wto_daily_payload_supports_split_schedule_intervals():
    payload = build_wto_daily_payload(
        branch_aa="0",
        employee_afm="123456789",
        employee_last_name="ΟΙΚΟΝΟΜΟΥ",
        employee_first_name="ΕΥΤΥΧΙΑ",
        reference_date="2026-07-03",
        schedule_type="ΕΡΓ",
        intervals=[
            {"hour_from": "09:00", "hour_to": "13:00"},
            {"hour_from": "17:00", "hour_to": "21:00"},
        ],
    )

    assert _analytics(payload) == [
        {"f_type": "ΕΡΓ", "f_from": "09:00", "f_to": "13:00"},
        {"f_type": "ΕΡΓ", "f_from": "17:00", "f_to": "21:00"},
    ]


def test_wto_daily_a_payload_matches_daily_structure():
    kwargs = dict(
        branch_aa="0",
        employee_afm="123456789",
        employee_last_name="ΟΙΚΟΝΟΜΟΥ",
        employee_first_name="ΕΥΤΥΧΙΑ",
        reference_date="2026-07-03",
        schedule_type="ΕΡΓ",
        hour_from="09:00",
        hour_to="17:00",
    )
    assert build_wto_daily_a_payload(**kwargs) == build_wto_daily_payload(**kwargs)


def test_wto_daily_payload_rejects_incomplete_split_interval():
    with pytest.raises(WorkCardPayloadError):
        build_wto_daily_payload(
            branch_aa="0",
            employee_afm="123456789",
            employee_last_name="ΟΙΚΟΝΟΜΟΥ",
            employee_first_name="ΕΥΤΥΧΙΑ",
            reference_date="2026-07-03",
            schedule_type="ΕΡΓ",
            intervals=[{"hour_from": "09:00", "hour_to": ""}],
        )
