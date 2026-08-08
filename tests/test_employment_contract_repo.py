"""Tests για hash / σύγκριση στοιχείων σύμβασης."""

from __future__ import annotations

from app.repo_employment_contract import content_hash_for_contract, _normalize_row


def test_content_hash_stable_for_same_fields():
    row = {
        "specialty": "ΣΕΡΒΙΤΟΡΟΣ",
        "characterization": "Α",
        "step92": "5131",
        "weekly_work_days": "6",
        "prior_service": "0",
        "employment_relation": "ΑΟΡΙΣΤΟΥ",
        "fixed_term_from": "",
        "fixed_term_to": "",
        "regime": "ΠΛΗΡΗΣ",
        "weekly_hours": "40",
        "salary": "1000",
        "hourly_wage": "",
        "total_weekly_hours": "40",
        "fulltime_contract_weekly_hours": "40",
        "break_minutes": 30,
        "break_in_work": 1,
        "flex_arrival_minutes": 120,
        "ergani_updated_at": "01/06/2026",
    }
    h1 = content_hash_for_contract(row)
    h2 = content_hash_for_contract({**row, "specialty": " ΣΕΡΒΙΤΟΡΟΣ "})
    assert h1 == h2
    assert len(h1) == 64


def test_content_hash_changes_on_field_or_ergani_date():
    base = {
        "specialty": "ΣΕΡΒΙΤΟΡΟΣ",
        "ergani_updated_at": "01/06/2026",
        "weekly_hours": "40",
        "flex_arrival_minutes": 120,
    }
    h0 = content_hash_for_contract(base)
    assert content_hash_for_contract({**base, "weekly_hours": "35"}) != h0
    assert content_hash_for_contract({**base, "ergani_updated_at": "02/06/2026"}) != h0


def test_normalize_row_keys_employer_branch_employee():
    data = _normalize_row(
        "802788173",
        "0",
        {
            "employee_afm": "141320107",
            "eponymo": "LUNGOLOVA",
            "onoma": "VERGINIYA",
            "specialty": "ΜΑΓΕΙΡΑΣ",
            "flex_arrival_minutes": "120",
            "break_in_work": "1",
        },
    )
    assert data["employer_afm"] == "802788173"
    assert data["branch_aa"] == "0"
    assert data["employee_afm"] == "141320107"
    assert data["flex_arrival_minutes"] == 120
    assert data["break_in_work"] == 1
    assert data["content_hash"]
