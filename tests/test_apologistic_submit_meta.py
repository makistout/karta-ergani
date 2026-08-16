import json

from app.apologistic_submit import overtime_submit_group_from_row, parse_wto_request_meta


def test_parse_wto_request_meta_extracts_overtime():
    payload = {
        "WTOS": {
            "WTO": [{
                "f_from_date": "04/08/2026",
                "Ergazomenoi": {
                    "ErgazomenoiWTO": [{
                        "f_afm": "149972558",
                        "f_date": "04/08/2026",
                        "ErgazomenosAnalytics": {
                            "ErgazomenosWTOAnalytics": [{"f_from": "19:32", "f_to": "20:28"}]
                        },
                    }]
                },
            }]
        }
    }
    afm, work_date, proposed = parse_wto_request_meta(json.dumps(payload))
    assert afm == "149972558"
    assert work_date == "04/08/2026"
    assert proposed == "19:32–20:28"


def test_cross_midnight_overtime_is_one_interval_on_its_start_date():
    reference_date, intervals = overtime_submit_group_from_row({
        "work_date": "18/08/2026",
        "overtime_minutes": 120,
        "overtime_segments": [
            {"date": "18/08/2026", "from": "23:00", "to": "01:00", "minutes": 120}
        ],
    })
    assert reference_date == "2026-08-18"
    assert intervals == [{
        "hour_from": "23:00",
        "hour_to": "01:00",
        "reference_date": "2026-08-18",
        "reference_date_ergani": "18/08/2026",
    }]
