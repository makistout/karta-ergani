"""Recovery of schedule_change when LLM returns unknown/alias."""

from app.telegram_assistant_service import validate_and_describe


def test_schedule_change_recovered_from_hours_when_intent_unknown():
    contexts = [{
        "store_id": 7,
        "store_name": "VILLA SHARM",
        "employer_afm": "123456789",
        "branch_aa": "0",
    }]
    employees = [{
        "store_id": 7,
        "afm": "180604475",
        "name": "ΜΟΥΡΑΤΙΔΟΥ ΑΛΕΞΑΝΔΡΑ",
    }]
    parsed = {
        "intent": "unknown",
        "store_id": 7,
        "employee_afms": ["180604475"],
        "employee_references": ["Μουρατιδου"],
        "date": "2026-08-22",
        "hour_from": "15:00",
        "hour_to": "21:40",
        "confidence": 0.9,
        "clarification_question": None,
    }
    status, validation, proposed = validate_and_describe(
        parsed,
        contexts=contexts,
        employees=employees,
        user_text="Στο villa sharm Μουρατιδου 22/8 15:00 έως 21:40 αλλαγή ωραρίου",
    )
    assert status == "draft"
    assert validation["valid"] is True
    assert parsed["intent"] == "schedule_change"
    assert "Αλλαγή ωραρίου" in proposed


def test_schedule_change_recovered_from_invented_intent_label():
    contexts = [{
        "store_id": 7,
        "store_name": "VILLA SHARM",
        "employer_afm": "123456789",
        "branch_aa": "0",
    }]
    employees = [{
        "store_id": 7,
        "afm": "180604475",
        "name": "ΜΟΥΡΑΤΙΔΟΥ ΑΛΕΞΑΝΔΡΑ",
    }]
    parsed = {
        "intent": "change_schedule",
        "store_id": 7,
        "employee_afms": ["180604475"],
        "employee_references": ["Μουρατιδου"],
        "date": "2026-08-22",
        "hour_from": "15:00",
        "hour_to": "21:40",
        "confidence": 0.9,
    }
    status, validation, proposed = validate_and_describe(
        parsed,
        contexts=contexts,
        employees=employees,
        user_text="Μουρατιδου 22/8 15:00 έως 21:40",
    )
    assert status == "draft"
    assert parsed["intent"] == "schedule_change"
    assert validation["valid"] is True
