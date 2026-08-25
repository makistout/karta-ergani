"""Tests για rule-based today_info + card punch fallback."""

from app.assistant_rule_fallback import (
    build_card_punch_command,
    build_today_info_answer,
    looks_like_card_punch,
    looks_like_today_info,
    rule_based_parse,
)


def test_looks_like_today_info():
    assert looks_like_today_info("Στο Ερατο ποιες κάρτες είναι ανοιχτές")
    assert looks_like_today_info("ποιοι εργάζονται ακόμα")
    assert not looks_like_today_info("άνοιξε κάρτα του Γιάννη")
    assert not looks_like_today_info("clock in κάρτα")


def test_looks_like_card_punch():
    assert looks_like_card_punch("άνοιξε κάρτα του Γιάννη")
    assert looks_like_card_punch("κλείσε κάρτα")
    assert looks_like_card_punch("clock in Sagar")
    assert looks_like_card_punch("clock out όλους")
    assert looks_like_card_punch("είσοδος κάρτας του Α")
    assert looks_like_card_punch("έξοδος κάρτας")
    assert not looks_like_card_punch("ποιες κάρτες είναι ανοιχτές")


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


def test_yesterday_open_cards_from_home_snapshot():
    today_home = {
        "date": "2026-08-23",
        "yesterday_date": "2026-08-22",
        "stores": [{"store_id": 9, "name": "ERATO", "employees": []}],
        "yesterday": {
            "date": "2026-08-22",
            "stores": [{
                "store_id": 9,
                "name": "ERATO",
                "employees": [
                    {"name": "OPEN Y", "afm": "1", "status": "needs_checkout", "card_in": "16:05"},
                ],
                "open_count": 1,
            }],
        },
    }
    text = build_today_info_answer(
        text="Υπάρχουν ανοιχτές κάρτες στο ερατο χθες;",
        store_id=9,
        store_name="ERATO",
        today_home=today_home,
    )
    assert text is not None
    assert "OPEN Y" in text
    assert "22/08/2026" in text
    parsed = rule_based_parse(
        text="ανοιχτές κάρτες χθες",
        store_id=9,
        store_name="ERATO",
        today_home=today_home,
    )
    assert parsed is not None
    assert parsed["date"] == "2026-08-22"


def test_yesterday_no_open_cards_is_explicit_zero():
    today_home = {
        "yesterday_date": "2026-08-22",
        "yesterday": {
            "date": "2026-08-22",
            "stores": [{"store_id": 9, "name": "ERATO", "employees": [], "open_count": 0}],
        },
    }
    text = build_today_info_answer(
        text="ανοιχτές κάρτες χθες",
        store_id=9,
        store_name="ERATO",
        today_home=today_home,
    )
    assert text is not None
    assert "δεν υπάρχουν ανοιχτές κάρτες" in text
    assert "διαθέσιμα δεδομένα" not in text


def test_card_punch_named_check_in():
    today_home = {
        "stores": [{
            "store_id": 9,
            "name": "ERATO",
            "employees": [
                {"name": "SAGAR YEASIN", "afm": "111", "status": "needs_checkin"},
            ],
        }]
    }
    employees = [{"store_id": 9, "afm": "111", "name": "SAGAR YEASIN"}]

    def resolve(text, emps, store_id):
        return ["111"] if "sagar" in text.casefold() else []

    parsed = build_card_punch_command(
        text="άνοιξε κάρτα sagar",
        store_id=9,
        today_home=today_home,
        employees=employees,
        resolve_afms=resolve,
    )
    assert parsed is not None
    assert parsed["intent"] == "card_check_in_now"
    assert parsed["employee_afms"] == ["111"]


def test_card_punch_clock_out_all_open():
    today_home = {
        "stores": [{
            "store_id": 9,
            "name": "ERATO",
            "employees": [
                {"name": "A", "afm": "1", "status": "at_work", "card_in": "10:00"},
                {"name": "B", "afm": "2", "status": "completed", "card_in": "09:00", "card_out": "17:00"},
                {"name": "C", "afm": "3", "status": "needs_checkout", "card_in": "12:00"},
            ],
        }]
    }
    parsed = build_card_punch_command(
        text="κλείσε όλες τις κάρτες",
        store_id=9,
        today_home=today_home,
    )
    assert parsed is not None
    assert parsed["intent"] == "card_check_out_now"
    assert set(parsed["employee_afms"]) == {"1", "3"}


def test_card_punch_retro_time():
    today_home = {
        "stores": [{
            "store_id": 9,
            "name": "ERATO",
            "employees": [{"name": "A", "afm": "1", "status": "needs_checkin"}],
        }]
    }
    employees = [{"store_id": 9, "afm": "1", "name": "A"}]
    parsed = build_card_punch_command(
        text="είσοδος κάρτας του A στις 16:00",
        store_id=9,
        today_home=today_home,
        employees=employees,
        resolve_afms=lambda t, e, s: ["1"],
    )
    assert parsed is not None
    assert parsed["intent"] == "card_check_in_retro"
    assert parsed["time"] == "16:00"


def test_card_punch_ambiguous_surname():
    today_home = {"stores": [{"store_id": 9, "name": "ERATO", "employees": []}]}
    employees = [
        {"store_id": 9, "afm": "1", "name": "VLASENKO IGOR"},
        {"store_id": 9, "afm": "2", "name": "VLASENKO KYRYLO"},
    ]
    parsed = build_card_punch_command(
        text="άνοιξε κάρτα vlasenko",
        store_id=9,
        today_home=today_home,
        employees=employees,
        resolve_afms=lambda t, e, s: ["1", "2"],
    )
    assert parsed is not None
    assert parsed["employee_afms"] == []
    assert set(parsed["ambiguous_employee_afms"]) == {"1", "2"}
    assert parsed["pending_intent"] == "card_check_in_now"
    assert "Εννοείτε" in (parsed.get("clarification_question") or "")


def test_card_punch_focus_afms():
    today_home = {
        "stores": [{
            "store_id": 9,
            "name": "ERATO",
            "employees": [{"name": "A", "afm": "1", "status": "at_work", "card_in": "10:00"}],
        }]
    }
    parsed = build_card_punch_command(
        text="κλείσε κάρτα",
        store_id=9,
        today_home=today_home,
        focus_afms=["1"],
    )
    assert parsed is not None
    assert parsed["intent"] == "card_check_out_now"
    assert parsed["employee_afms"] == ["1"]
