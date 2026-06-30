from app.portal_work_log_sync import _dedupe_work_log_day_items
from app.card_report import build_card_status_report
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


def test_card_report_uses_card_event_fallback_for_missing_exit(monkeypatch):
    monkeypatch.setattr(
        "app.card_report.list_schedule_for_store",
        lambda employer_afm, branch_aa, work_date: [
            {
                "employee_afm": "111111111",
                "eponymo": "Existing",
                "onoma": "Row",
                "hour_from": "12:00",
                "hour_to": "20:00",
                "shift_type": "ΕΡΓΑΣΙΑ",
            }
        ],
    )
    monkeypatch.setattr(
        "app.card_report.list_work_log_for_store",
        lambda employer_afm, branch_aa, work_date: [
            {
                "employee_afm": "111111111",
                "work_date": "29/06/2026",
                "hour_from": "12:00",
                "hour_to": "",
                "eponymo": "Existing",
                "onoma": "Row",
            }
        ],
    )
    monkeypatch.setattr(
        "app.repo_work_log._card_db_details_by_employee_work_date",
        lambda employer_afm, branch_aa, dates: {
            ("111111111", "29/06/2026"): {
                "types": {"1"},
                "check_in": None,
                "check_out": {"time": "20:00", "eponymo": "Existing", "onoma": "Row"},
            }
        },
    )
    monkeypatch.setattr("app.card_report.list_card_events_for_store_date", lambda *args, **kwargs: [])
    monkeypatch.setattr("app.card_report.flex_arrival_map_for_employer", lambda *args, **kwargs: {})

    report = build_card_status_report("123456789", "0", date_iso="2026-06-29")
    row = report["rows"][0]

    assert row["work_log"]["hour_to"] == "20:00"
    assert row["status"] == "completed"
    assert row["status_label"] == "Ολοκληρωμένη μέρα"
