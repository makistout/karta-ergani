from scripts.export_apologistic_oraria_katalogos import (
    _collect,
    _opening_closing_punch,
    _parse_punch_parts,
)


def test_catalog_uses_canonical_intervals_and_never_proposed_as_recognized():
    day = {
        "employee_afm": "123456789",
        "work_date": "17/08/2026",
        "status": "change",
        "proposed": "09:00–18:00",
        "basis_label": "09:00–17:00",
        "overwork_interval": "17:00–18:00",
        "overwork_from": "17:00",
        "overwork_to": "18:00",
        "overwork_minutes": 60,
        "punch_recorded": "09:00–18:00",
    }

    recognized, overwork, _, _, detail = _collect([day])

    assert recognized == [("09:00", "17:00")]
    assert recognized != [("09:00", "18:00")]
    assert overwork == [("17:00", "18:00")]
    assert detail[0]["basis_label"] == day["basis_label"]
    assert detail[0]["proposed"] == day["proposed"]


def test_catalog_never_falls_back_to_proposed_for_review_row():
    day = {
        "employee_afm": "123456789",
        "work_date": "17/08/2026",
        "status": "review",
        "proposed": "09:00–18:00",
        "punch_recorded": "09:00–18:00",
    }

    recognized, overwork, _, punches, detail = _collect([day])

    assert recognized == []
    assert overwork == []
    assert punches == [("09:00", "18:00")]
    assert detail[0]["basis_label"] == ""


def test_catalog_punch_cells_use_complete_opening_and_closing_not_orphan():
    day = {
        "employee_afm": "043031180",
        "work_date": "28/06/2026",
        "status": "change",
        "proposed": "13:00–19:40",
        "basis_label": "13:01–19:41",
        "overwork_interval": "20:04–21:24",
        "overwork_from": "20:04",
        "overwork_to": "21:24",
        "overwork_minutes": 80,
        "punch_recorded": "–13:01\n13:24–19:41",
    }

    _, _, _, punches, detail = _collect([day])

    assert detail[0]["punch_from"] == "13:24"
    assert detail[0]["punch_to"] == "19:41"
    assert detail[0]["punch_from"] != day["basis_label"].split("–")[0]
    assert punches == [("13:24", "19:41")]


def test_opening_closing_punch_keeps_true_single_boundary_empty():
    assert _opening_closing_punch(_parse_punch_parts("–21:05")) == (None, "21:05")
    assert _opening_closing_punch(_parse_punch_parts("09:00–")) == ("09:00", None)
    assert _opening_closing_punch(
        _parse_punch_parts("13:00–17:09\n20:00–00:05*")
    ) == ("13:00", "00:05")
