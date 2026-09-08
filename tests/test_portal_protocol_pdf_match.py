"""Unit tests for protocol PDF content parsing / section detection."""

from __future__ import annotations

from app.portal_protocol_pdf_match import (
    extract_select_items_from_html,
    find_protocol_pdf_path,
    index_protocol_pdfs_for_range,
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
