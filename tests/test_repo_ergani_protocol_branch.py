"""Tests for protocol branch filtering."""

from app.repo_ergani_protocol import parse_card_protocol_export_rows


def test_parse_card_protocol_keeps_only_store_branch():
    rows = [
        ["Παράρτημα", "Κατάσταση", "Είδος", "Ημ/νία", "Πρωτόκολλο", "Εκπρόθεσμο"],
        ["4", "Υποβληθείσα", "Δήλωση έναρξης/λήξης εργασίας εργαζομένων", "08/09/2026 16:00", "ΚΕ111", "Όχι"],
        ["1", "Υποβληθείσα", "Δήλωση έναρξης/λήξης εργασίας εργαζομένων", "08/09/2026 16:01", "ΚΕ222", "Όχι"],
        ["4", "Υποβληθείσα", "Δήλωση έναρξης/λήξης εργασίας εργαζομένων", "08/09/2026 16:02", "ΚΕ333", "Όχι"],
    ]
    parsed = parse_card_protocol_export_rows(
        rows, employer_afm="803229207", branch_aa="4"
    )
    assert [p["protocol"] for p in parsed] == ["ΚΕ111", "ΚΕ333"]
    assert all(p["branch_aa"] == "4" for p in parsed)
