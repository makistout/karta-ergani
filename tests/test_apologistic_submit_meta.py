import json

from app.apologistic_submit import parse_wto_request_meta


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
