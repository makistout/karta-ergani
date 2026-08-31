import pytest

from app.wto_daily_payload import build_wto_daily_a_batch_payload, build_wto_daily_a_payload
from app.wto_ov_payload import build_wto_ov_a_batch_payload, build_wto_ov_a_payload
from app.work_card_payload import WorkCardPayloadError


def _employees(payload):
    return payload["WTOS"]["WTO"][0]["Ergazomenoi"]["ErgazomenoiWTO"]


def test_wto_daily_a_batch_payload_multiple_employees():
    payload = build_wto_daily_a_batch_payload(
        branch_aa="0",
        employees=[
            {
                "employee_afm": "123456789",
                "employee_last_name": "ΠΑΠΑ",
                "employee_first_name": "ΜΑΡΙΑ",
                "reference_date": "2026-07-28",
                "schedule_type": "ΕΡΓ",
                "hour_from": "09:00",
                "hour_to": "17:00",
            },
            {
                "employee_afm": "987654321",
                "employee_last_name": "ΒΗΧΟΣ",
                "employee_first_name": "ΙΩΑΝΝΗΣ",
                "reference_date": "2026-07-29",
                "schedule_type": "ΕΡΓ",
                "hour_from": "10:00",
                "hour_to": "18:00",
            },
        ],
    )
    employees = _employees(payload)
    assert len(employees) == 2
    assert employees[0]["f_afm"] == "123456789"
    assert employees[1]["f_afm"] == "987654321"
    wto = payload["WTOS"]["WTO"][0]
    assert wto["f_from_date"] == "28/07/2026"
    assert wto["f_to_date"] == "29/07/2026"


def test_wto_daily_a_batch_matches_single_employee_payload():
    kwargs = dict(
        branch_aa="0",
        employee_afm="123456789",
        employee_last_name="ΠΑΠΑ",
        employee_first_name="ΜΑΡΙΑ",
        reference_date="2026-07-28",
        schedule_type="ΕΡΓ",
        hour_from="09:00",
        hour_to="17:00",
    )
    single = build_wto_daily_a_payload(**kwargs)
    batch = build_wto_daily_a_batch_payload(
        branch_aa="0",
        employees=[{
            "employee_afm": kwargs["employee_afm"],
            "employee_last_name": kwargs["employee_last_name"],
            "employee_first_name": kwargs["employee_first_name"],
            "reference_date": kwargs["reference_date"],
            "schedule_type": kwargs["schedule_type"],
            "hour_from": kwargs["hour_from"],
            "hour_to": kwargs["hour_to"],
        }],
    )
    assert batch == single


def test_wto_daily_a_batch_requires_employees():
    with pytest.raises(WorkCardPayloadError):
        build_wto_daily_a_batch_payload(branch_aa="0", employees=[])


def test_wto_ov_a_batch_payload_multiple_employees():
    payload = build_wto_ov_a_batch_payload(
        branch_aa="0",
        employees=[
            {
                "employee_afm": "123456789",
                "employee_last_name": "ΠΑΠΑ",
                "employee_first_name": "ΜΑΡΙΑ",
                "reference_date": "2026-07-28",
                "hour_from": "21:00",
                "hour_to": "22:00",
            },
            {
                "employee_afm": "987654321",
                "employee_last_name": "ΒΗΧΟΣ",
                "employee_first_name": "ΙΩΑΝΝΗΣ",
                "reference_date": "2026-07-28",
                "hour_from": "20:00",
                "hour_to": "21:00",
            },
        ],
    )
    assert len(_employees(payload)) == 2
    analytics = _employees(payload)[0]["ErgazomenosAnalytics"]["ErgazomenosWTOAnalytics"]
    assert analytics[0]["f_type"] == "ΥΠ"


def test_wto_ov_a_batch_matches_single_payload():
    kwargs = dict(
        branch_aa="0",
        employee_afm="123456789",
        employee_last_name="ΠΑΠΑΔΟΠΟΥΛΟΣ",
        employee_first_name="ΝΙΚΟΣ",
        reference_date="2026-07-28",
        hour_from="21:00",
        hour_to="23:00",
    )
    assert build_wto_ov_a_batch_payload(branch_aa="0", employees=[{
        "employee_afm": kwargs["employee_afm"],
        "employee_last_name": kwargs["employee_last_name"],
        "employee_first_name": kwargs["employee_first_name"],
        "reference_date": kwargs["reference_date"],
        "hour_from": kwargs["hour_from"],
        "hour_to": kwargs["hour_to"],
    }]) == build_wto_ov_a_payload(**kwargs)
