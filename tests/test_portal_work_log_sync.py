from app.portal_work_log_sync import _dedupe_work_log_day_items


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
