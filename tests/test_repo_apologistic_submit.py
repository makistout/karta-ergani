from datetime import date
import json

from app.repo_apologistic import (
    _exchange_replacement_state,
    _overtime_minutes_from_request_json,
    _submit_entry_from_row,
)
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY_A


def test_submit_entry_marks_proposal_mismatch():
    entry = _submit_entry_from_row(
        {"protocol": "P1", "proposed_at_submit": "08:00–16:00", "submit_date_text": "2026-08-03"},
        proposed="09:00–17:00",
    )
    assert entry["matches_proposal"] is False


def test_exchange_preserves_non_work_state_for_replacement_day():
    assert _exchange_replacement_state({
        "declared": "ΜΗ ΕΡΓΑΣΙΑ", "day_state": "Μη εργασία",
    }) == ("ΜΗ ΕΡΓΑΣΙΑ", "Μη εργασία")


def test_exchange_preserves_rest_state_for_replacement_day():
    assert _exchange_replacement_state({
        "declared": "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "day_state": "Ρεπό",
    }) == ("ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "Ρεπό")


def test_submit_entry_marks_proposal_match():
    entry = _submit_entry_from_row(
        {"protocol": "P1", "proposed_at_submit": "09:00–17:00"},
        proposed="09:00–17:00",
    )
    assert entry["matches_proposal"] is True


def test_attach_ergani_submits_groups_latest_per_kind():
    report = {
        "days": [
            {
                "employee_afm": "123456789",
                "work_date": "03/08/2026",
                "proposed": "09:00–17:00",
            }
        ]
    }
    rows = [
        {
            "employee_afm": "123456789",
            "work_date": date(2026, 8, 3),
            "submission_code": SUBMISSION_CODE_WTO_DAILY_A,
            "proposed_at_submit": "09:00–17:00",
            "segment_reference_date": None,
            "protocol": "NEW",
            "ergani_submission_id": "2",
            "submit_date_text": "d2",
            "declaration_id": 11,
            "submitted_at": "2026-08-11T10:00:00",
        },
        {
            "employee_afm": "123456789",
            "work_date": date(2026, 8, 3),
            "submission_code": SUBMISSION_CODE_WTO_DAILY_A,
            "proposed_at_submit": "08:00–16:00",
            "segment_reference_date": None,
            "protocol": "OLD",
            "ergani_submission_id": "1",
            "submit_date_text": "d1",
            "declaration_id": 10,
            "submitted_at": "2026-08-10T10:00:00",
        },
    ]
    latest = {}
    for row in rows:
        key = (
            str(row["employee_afm"]),
            row["work_date"].strftime("%d/%m/%Y"),
            str(row["submission_code"]),
            None,
        )
        if key in latest:
            continue
        item = dict(row)
        item["segment_date"] = None
        latest[key] = item
    for day in report["days"]:
        afm = str(day["employee_afm"])
        wd = str(day["work_date"])
        proposed = str(day["proposed"])
        schedule = latest.get((afm, wd, SUBMISSION_CODE_WTO_DAILY_A, None))
        if schedule:
            day["ergani_submit"] = {
                "schedule": _submit_entry_from_row(schedule, proposed=proposed),
            }
    submit = report["days"][0]["ergani_submit"]["schedule"]
    assert submit["protocol"] == "NEW"
    assert submit["matches_proposal"] is True


def test_overtime_minutes_are_read_from_submission_payload():
    payload = {
        "WTOS": {"WTO": [{"Ergazomenoi": {"ErgazomenoiWTO": [{
            "ErgazomenosAnalytics": {"ErgazomenosWTOAnalytics": [
                {"f_from": "21:30", "f_to": "23:00"},
                {"f_from": "23:30", "f_to": "00:30"},
            ]}
        }]}}]}
    }
    assert _overtime_minutes_from_request_json(json.dumps(payload)) == 150
