from app.apologistic_export import build_apologistic_export_xlsx


def test_build_apologistic_export_xlsx_contains_headers_and_rows():
    content = build_apologistic_export_xlsx(
        meta_line="ΥΑΔΕΣ · 29/06–05/07 · φίλτρο: Για έλεγχο",
        headers=["Ημέρα", "Εργαζόμενος", "Πρόταση"],
        rows=[
            ["01/07/2026", "ΑΘΑΝΑΣΙΟΥ ΓΕΩΡΓΙΟΣ", "17:55–00:57"],
            ["29/06/2026", "ΛΟΥΡΑΣ ΦΩΤΙΟΣ", "09:00–17:00"],
        ],
    )
    assert content[:2] == b"PK"
    assert len(content) > 2000
