"""Safety net: open/close intent must match explicit user wording."""

from app.assistant_card_intent import card_action_direction_from_text, correct_card_intent_from_text
from app.telegram_assistant_service import validate_and_describe


def test_detect_open_from_greek_and_english():
    assert card_action_direction_from_text("Στο villa sharm άνοιξε τη κάρτα στον enkid") == "check_in"
    assert card_action_direction_from_text("κάνε clock in στον enkid haxhi") == "check_in"
    assert card_action_direction_from_text("κλείσε την κάρτα") == "check_out"
    assert card_action_direction_from_text("Κλειστόν") == "check_out"
    assert card_action_direction_from_text("clock out please") == "check_out"


def test_info_query_with_open_adjective_not_action():
    assert card_action_direction_from_text("ποιος έχει ανοιχτή κάρτα") is None


def test_corrects_wrong_llm_close_to_open():
    contexts = [{
        "store_id": 7,
        "store_name": "VILLA SHARM",
        "employer_afm": "123456789",
        "branch_aa": "0",
    }]
    employees = [{
        "store_id": 7,
        "afm": "111222333",
        "name": "HAXHI ENKID",
    }]
    parsed = {
        "intent": "card_check_out_now",
        "store_id": 7,
        "employee_afms": ["111222333"],
        "date": "2026-08-22",
        "time": None,
    }
    validate_and_describe(
        parsed,
        contexts=contexts,
        employees=employees,
        user_text="Στο villa sharm άνοιξε τη κάρτα στον enkid",
    )
    assert parsed["intent"] == "card_check_in_now"


def test_corrects_wrong_llm_open_to_close():
    parsed = {
        "intent": "card_check_in_now",
        "store_id": 7,
        "employee_afms": ["111222333"],
        "date": "2026-08-22",
    }
    assert correct_card_intent_from_text(parsed, "κλείσε την κάρτα του enkid") is True
    assert parsed["intent"] == "card_check_out_now"


def test_all_skipped_card_shows_explanatory_single_line():
    contexts = [{
        "store_id": 7,
        "store_name": "VILLA SHARM",
        "employer_afm": "123456789",
        "branch_aa": "0",
    }]
    employees = [{
        "store_id": 7,
        "afm": "111222333",
        "name": "HAXHI ENKID",
    }]
    parsed = {
        "intent": "card_check_in_now",
        "store_id": 7,
        "employee_afms": ["111222333"],
        "date": "2026-08-22",
        "time": None,
    }

    from unittest.mock import patch

    with patch(
        "app.work_card_guards.new_card_punch_blocked_reason",
        return_value="Δεν γίνεται άνοιγμα — υπάρχει ήδη δήλωση εισόδου στις 12:40.",
    ):
        status, _validation, proposed = validate_and_describe(
            parsed,
            contexts=contexts,
            employees=employees,
            user_text="κάνε clock in στον enkid",
        )

    assert status == "answered"
    assert proposed == (
        "HAXHI ENKID: Δεν γίνεται άνοιγμα — υπάρχει ήδη δήλωση εισόδου στις 12:40."
    )
