"""Tests για rule-based today_info fallback."""

from app.assistant_rule_fallback import build_today_info_answer, looks_like_today_info, rule_based_parse


def test_looks_like_today_info():
    assert looks_like_today_info("Στο Ερατο ποιες κάρτες είναι ανοιχτές")
    assert looks_like_today_info("ποιοι εργάζονται ακόμα")
    assert not looks_like_today_info("άνοιξε κάρτα του Γιάννη")


def test_build_open_cards_answer():
    today_home = {
        "stores": [{
            "store_id": 9,
            "name": "ERATO",
            "employees": [
                {"name": "A", "afm": "1", "status": "at_work", "card_in": "15:02:00", "schedule_to": "21:40"},
                {"name": "B", "afm": "2", "status": "completed", "card_in": "12:00", "card_out": "18:00"},
            ],
        }]
    }
    text = build_today_info_answer(
        text="ποιες κάρτες είναι ανοιχτές",
        store_id=9,
        store_name="ERATO",
        today_home=today_home,
    )
    assert text is not None
    assert "ανοιχτές" in text
    assert "A" in text
    assert "B" not in text


def test_rule_based_parse_today_info():
    today_home = {
        "stores": [{
            "store_id": 9,
            "name": "ERATO",
            "employees": [
                {"name": "A", "afm": "1", "status": "at_work", "card_in": "15:02"},
            ],
        }]
    }
    parsed = rule_based_parse(
        text="Στο Ερατο ποιοι εργάζονται ακόμα",
        store_id=9,
        store_name="ERATO",
        today_home=today_home,
    )
    assert parsed is not None
    assert parsed["intent"] == "today_info"
    assert "A" in parsed["clarification_question"]
