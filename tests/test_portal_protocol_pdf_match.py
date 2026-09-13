"""Unit tests for protocol PDF content parsing / section detection."""

from __future__ import annotations

from app.portal_protocol_pdf_match import (
    extract_select_items_from_html,
    find_protocol_pdf_path,
    index_protocol_pdfs_for_range,
    match_work_logs_for_pdf_row,
    parse_protocol_pdf_text,
)


def test_parse_pdf_arrival_only():
    text = """
Γ. ΠΕΡΙΕΧΟΜΕΝΟ ΔΗΛΩΣΗΣ
ΑΦΜ ΟΝΟΜΑΤΕΠΩΝΥΜΟ
ΗΜΕΡΑ ΩΡΑ
ΠΡΟΣΕΛΕΥΣΗΣ
162707131 ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ
01/06/2026 12:01

ΑΦΜ ΟΝΟΜΑΤΕΠΩΝΥΜΟ
ΗΜΕΡΑ ΩΡΑ
ΑΠΟΧΩΡΗΣΗΣ
"""
    parsed = parse_protocol_pdf_text(text, filename="ΚΕ195164713_802314187.pdf")
    assert parsed["protocol"] == "ΚΕ195164713"
    assert parsed["in_row"]["afm"] == "162707131"
    assert parsed["in_row"]["time"] == "12:01"
    assert parsed["out_row"] is None


def test_parse_pdf_exit_only():
    text = """
Γ. ΠΕΡΙΕΧΟΜΕΝΟ ΔΗΛΩΣΗΣ
ΑΦΜ ΟΝΟΜΑΤΕΠΩΝΥΜΟ ΗΜΕΡΑ ΩΡΑ ΠΡΟΣΕΛΕΥΣΗΣ
ΑΦΜ ΟΝΟΜΑΤΕΠΩΝΥΜΟ ΗΜΕΡΑ ΩΡΑ ΑΠΟΧΩΡΗΣΗΣ
043031180 ΝΤΟΥΛΙΑΣ ΠΑΡΑΣΕΚΥΑΣ 01/09/2026 18:50
"""
    parsed = parse_protocol_pdf_text(text, filename="ΚΕ999.pdf")
    assert parsed["in_row"] is None
    assert parsed["out_row"]["afm"] == "043031180"
    assert parsed["out_row"]["time"] == "18:50"
    assert parsed["out_row"]["day"] == "01/09/2026"


def test_find_protocol_pdf_path(tmp_path):
    day = tmp_path / "091065232" / "0" / "2026-06-01"
    day.mkdir(parents=True)
    pdf = day / "ΚΕ195164713_802314187.pdf"
    pdf.write_bytes(b"%PDF" + b"0" * 2000)
    found = find_protocol_pdf_path(
        "091065232", "0", "2026-06-01", "ΚΕ195164713", root=tmp_path
    )
    assert found == pdf
    indexed = index_protocol_pdfs_for_range(
        "091065232", "0", "2026-06-01", "2026-06-01", root=tmp_path
    )
    assert "ΚΕ195164713" in indexed


def test_match_overnight_exit_uses_pdf_work_date():
    """PDF στον φάκελο 13/09 με ημέρα βάρδιας 12/09 → βρίσκει overnight έξοδο."""
    wls = [
        {
            "id": 1,
            "employee_afm": "170809878",
            "hour_from": "14:07",
            "hour_to": "00:03",
            "work_date": "12/09/2026",
            "protocol_to": None,
        },
        {
            "id": 2,
            "employee_afm": "170809878",
            "hour_from": "14:00",
            "hour_to": "00:03",
            "work_date": "13/09/2026",
            "protocol_to": None,
        },
    ]
    matches = match_work_logs_for_pdf_row(
        wls,
        kind="out",
        row={"afm": "170809878", "time": "00:03", "day": "12/09/2026"},
    )
    assert len(matches) == 1
    assert matches[0]["id"] == 1
