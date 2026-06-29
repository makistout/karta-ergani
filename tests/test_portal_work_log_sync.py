from app.portal_work_log_sync import _dedupe_work_log_day_items
from app.repo_work_log import append_card_punches_missing_from_work_log


def test_dedupe_work_log_prefers_row_with_exit():
    rows = [
        {
            "employee_afm": "169914313",
            "eponymo": "MD MOHAMMAD",
            "onoma": "ASIF",
            "work_date": "26/06/2026",
            "hour_from": "08:00",
            "hour_to": "",
            "source_aa": "1",
        },
        {
            "employee_afm": "169914313",
            "eponymo": "MD MOHAMMAD",
            "onoma": "ASIF",
            "work_date": "26/06/2026",
            "hour_from": "08:00",
            "hour_to": "16:05",
            "source_aa": "1",
        },
    ]

    deduped = _dedupe_work_log_day_items(rows)

    assert len(deduped) == 1
    assert deduped[0]["hour_to"] == "16:05"


def test_append_card_punches_missing_from_work_log(monkeypatch):
    rows = [
        {
            "employee_afm": "111111111",
            "work_date": "29/06/2026",
            "hour_from": "09:00",
            "hour_to": "",
        }
    ]

    def fake_card_details(employer_afm, branch_aa, dates):
        return {
            ("111111111", "29/06/2026"): {
                "types": {"0", "1"},
                "check_in": {"time": "09:00", "eponymo": "Existing", "onoma": "Row"},
                "check_out": {"time": "17:00", "eponymo": "Existing", "onoma": "Row"},
            },
            ("222222222", "29/06/2026"): {
                "types": {"0"},
                "check_in": {
                    "time": "10:12",
                    "eponymo": "Card",
                    "onoma": "Only",
                    "protocol": "P1",
                },
                "check_out": None,
            },
        }

    monkeypatch.setattr(
        "app.repo_work_log._card_db_details_by_employee_work_date",
        fake_card_details,
    )

    out = append_card_punches_missing_from_work_log(
        rows,
        "123456789",
        "0",
        ["29/06/2026"],
    )

    assert len(out) == 2
    existing = [r for r in out if r.get("employee_afm") == "111111111"][0]
    assert existing["hour_to"] == "17:00"
    assert existing["hour_to_source"] == "card_event_fallback"
    assert existing["from_card_event_fallback"] is True
    fallback = [r for r in out if r.get("employee_afm") == "222222222"][0]
    assert fallback["hour_from"] == "10:12"
    assert fallback["hour_to"] == ""
    assert fallback["from_card_event_fallback"] is True
    assert fallback["source_aa"] == "card_event_fallback"
