from unittest.mock import patch

from app.telegram_assistant_service import (
    _format_name_choices,
    _ambiguous_name_candidates,
    _first_name_in_text,
    validate_and_describe,
)


def _emp(afm: str, name: str, store_id: int = 4) -> dict:
    return {"afm": afm, "name": name, "store_id": store_id}


def _ctx():
    return [{"store_id": 4, "store_name": "ERATO", "employer_afm": "123456789", "branch_aa": "0"}]


def test_format_name_choices_uses_gendered_articles():
    text = _format_name_choices([
        _emp("111111111", "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"),
        _emp("222222222", "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ"),
        _emp("333333333", "ΦΩΤΟΠΟΥΛΟΥ ΕΛΕΝΗ"),
    ])
    assert text.startswith("Εννοείτε ")
    assert text.count("του ") == 2
    assert "της " in text
    assert "Κωνσταντινου" in text
    assert "Διονυσιου" in text
    assert "Ελενης" in text
    assert text.endswith(";")


def test_similar_fotopoulos_surname_needs_all_choices():
    employees = [
        _emp("111111111", "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"),
        _emp("222222222", "ΦΩΤΟΠΟΥΛΟΥ ΕΛΕΝΗ"),
        _emp("333333333", "ΠΑΠΑΔΟΠΟΥΛΟΣ ΓΙΩΡΓΟΣ"),
    ]
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, _ = validate_and_describe(
            {
                "intent": "card_check_in_now",
                "store_id": 4,
                "employee_afms": ["222222222"],
                "employee_references": ["φωτοπουλου"],
                "date": "2026-08-20",
                "time": None,
                "confidence": 0.9,
            },
            contexts=_ctx(),
            employees=employees,
            user_text="άνοιξε την κάρτα του φωτοπουλου",
        )
    assert status == "needs_clarification"
    errors = " ".join(validation["errors"])
    assert "Εννοείτε" in errors
    assert "Κωνσταντινου" in errors
    assert "Ελενης" in errors


def test_same_surname_vlasenko_needs_clarification():
    employees = [
        _emp("111111111", "VLASENKO IGOR"),
        _emp("222222222", "VLASENKO KYRYLO"),
    ]
    candidates = _ambiguous_name_candidates(
        "άνοιξε κάρτα vlasenko", employees, 4, ["111111111"],
    )
    assert {row["afm"] for row in candidates} == {"111111111", "222222222"}
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, _ = validate_and_describe(
            {
                "intent": "card_check_in_now",
                "store_id": 4,
                "employee_afms": ["111111111"],
                "employee_references": ["vlasenko"],
                "date": "2026-08-20",
                "confidence": 0.9,
            },
            contexts=_ctx(),
            employees=employees,
            user_text="άνοιξε κάρτα vlasenko",
        )
    assert status == "needs_clarification"
    errors = " ".join(validation["errors"]).upper()
    assert "IGOR" in errors and "KYRYLO" in errors


def test_unique_first_name_disambiguates_similar_surnames():
    employees = [
        _emp("111111111", "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"),
        _emp("222222222", "ΦΩΤΟΠΟΥΛΟΥ ΕΛΕΝΗ"),
    ]
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, proposed = validate_and_describe(
            {
                "intent": "card_check_in_now",
                "store_id": 4,
                "employee_afms": ["222222222"],
                "employee_references": ["ελενη"],
                "date": "2026-08-20",
                "confidence": 0.9,
            },
            contexts=_ctx(),
            employees=employees,
            user_text="άνοιξε την κάρτα της ελενης φωτοπουλου",
        )
    assert status == "draft"
    assert validation["valid"] is True
    assert "ΕΛΕΝΗ" in proposed


def test_first_name_helpers_still_work_for_safety_net():
    assert _first_name_in_text("Διονυσιου", "ΔΙΟΝΥΣΙΟΣ")
    assert _first_name_in_text("του Κωνσταντινου", "ΚΩΝΣΤΑΝΤΙΝΟΣ")


def test_name_choice_reply_skips_python_ambiguity_reask():
    employees = [
        _emp("111111111", "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"),
        _emp("222222222", "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ"),
    ]
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, proposed = validate_and_describe(
            {
                "intent": "card_check_in_now",
                "store_id": 4,
                "employee_afms": ["222222222"],
                "date": "2026-08-20",
                "confidence": 0.9,
            },
            contexts=_ctx(),
            employees=employees,
            reply_context={
                "pending_clarification": {
                    "kind": "name_choice",
                    "candidate_afms": ["111111111", "222222222"],
                }
            },
            user_text="dionisi",
        )
    assert status == "draft"
    assert validation["valid"] is True
    assert "ΔΙΟΝΥΣΙΟΣ" in proposed.upper()


def test_ambiguity_persists_candidate_afms():
    employees = [
        _emp("111111111", "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"),
        _emp("222222222", "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ"),
    ]
    parsed = {
        "intent": "card_check_in_now",
        "store_id": 4,
        "employee_afms": ["111111111"],
        "date": "2026-08-20",
        "confidence": 0.9,
    }
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, _ = validate_and_describe(
            parsed,
            contexts=_ctx(),
            employees=employees,
            user_text="άνοιξε την κάρτα του φωτοπουλου",
        )
    assert status == "needs_clarification"
    assert set(parsed.get("ambiguous_employee_afms") or []) == {"111111111", "222222222"}
    assert parsed.get("employee_afms") == []
