from unittest.mock import patch

from app.telegram_assistant_service import (
    _assistant_prompt_guide,
    _first_name_in_text,
    validate_and_describe,
)


def _emp(afm: str, name: str, store_id: int = 4) -> dict:
    return {"afm": afm, "name": name, "store_id": store_id}


def _ctx():
    return [{"store_id": 4, "store_name": "ERATO", "employer_afm": "123456789", "branch_aa": "0"}]


def test_prompt_guide_prefers_multi_name_over_false_ambiguity():
    guide = " ".join(_assistant_prompt_guide())
    assert "Πολλά ονόματα" in guide or "πολλά ονόματα" in guide.casefold()
    assert "ambiguous_employee_afms" in guide
    assert "ΜΗΝ ρωτάς" in guide or "μην ρωτας" in guide.casefold()


def test_distinct_surnames_from_gemini_become_draft():
    """Kanakis + Uzzal: trust LLM AFMs — no Python «Εννοείτε Mohammad ή Stylianos»."""
    employees = [
        _emp("111111111", "ΚΑΝΑΚΗΣ ΣΤΥΛΙΑΝΟΣ"),
        _emp("222222222", "UZZAL MOHAMMAD"),
    ]
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, proposed = validate_and_describe(
            {
                "intent": "card_check_in_retro",
                "store_id": 4,
                "employee_afms": ["111111111", "222222222"],
                "employee_references": ["κανακη", "uzzal"],
                "date": "2026-08-20",
                "time": "15:05",
                "confidence": 0.95,
            },
            contexts=_ctx(),
            employees=employees,
            user_text="ανοιξε την καρτα του κανακη και του uzzal πριν 10 λεπτα",
        )
    assert status == "draft"
    assert validation["valid"] is True
    assert "Εννοείτε" not in " ".join(validation["errors"])
    assert "ΚΑΝΑΚΗΣ" in proposed.upper()
    assert "UZZAL" in proposed.upper()


def test_gemini_name_ambiguity_persists_candidates_without_python_rewrite():
    """When Gemini asks Εννοείτε…, keep its ambiguous AFMs for the follow-up."""
    employees = [
        _emp("111111111", "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"),
        _emp("222222222", "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ"),
    ]
    parsed = {
        "intent": "unknown",
        "store_id": 4,
        "employee_afms": [],
        "ambiguous_employee_afms": ["111111111", "222222222"],
        "clarification_question": "Εννοείτε του Κωνσταντινου ή του Διονυσιου;",
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
    assert "Εννοείτε" in " ".join(validation["errors"])
    assert set(parsed.get("ambiguous_employee_afms") or []) == {"111111111", "222222222"}
    assert parsed.get("employee_afms") == []


def test_python_does_not_force_fotopoulos_clarification_when_llm_picks_one():
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
                "employee_references": ["φωτοπουλου"],
                "date": "2026-08-20",
                "confidence": 0.9,
            },
            contexts=_ctx(),
            employees=employees,
            user_text="άνοιξε την κάρτα του φωτοπουλου",
        )
    assert status == "draft"
    assert validation["valid"] is True
    assert "Εννοείτε" not in " ".join(validation["errors"])
    assert "ΕΛΕΝΗ" in proposed.upper()


def test_name_choice_reply_still_drafts():
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


def test_group_schedule_query_does_not_reask_previous_fotopoulos():
    employees = [
        _emp("111111111", "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"),
        _emp("222222222", "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ"),
        _emp("333333333", "ΠΑΠΑΔΟΠΟΥΛΟΣ ΓΙΩΡΓΟΣ"),
    ]
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, _ = validate_and_describe(
            {
                "intent": "card_check_in_now",
                "store_id": 4,
                "employee_afms": ["333333333"],
                "date": "2026-08-20",
                "confidence": 0.9,
            },
            contexts=_ctx(),
            employees=employees,
            reply_context={"employee_afms": ["111111111"], "store_id": 4},
            user_text="άνοιξε την κάρτα σε όσους δουλεύουν μετά τις 2μμ",
        )
    errors = " ".join(validation["errors"])
    assert "Εννοείτε" not in errors
    assert status in {"draft", "needs_clarification"}


def test_first_name_helpers_still_work_for_focus_mining():
    assert _first_name_in_text("Διονυσιου", "ΔΙΟΝΥΣΙΟΣ")
    assert _first_name_in_text("του Κωνσταντινου", "ΚΩΝΣΤΑΝΤΙΝΟΣ")
