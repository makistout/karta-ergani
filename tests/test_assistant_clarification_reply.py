from app.assistant_conversation_service import (
    _is_affirmative,
    _is_negative,
    _offers_cancel,
    process_assistant_command,
)
import json


def test_named_store_ignores_pending_from_other_store(monkeypatch):
    """«Στο Ερατο…» δεν συνεχίζει ανοιχτή εντολή Training Room."""
    calls: list[dict] = []

    def fake_pending(**kwargs):
        calls.append(dict(kwargs))
        # Chat-scoped pending points at Training Room; message names ERATO.
        return {
            "id": 44,
            "store_id": 4,
            "recipient_id": 8,
            "task_status": "needs_clarification",
            "proposed_action_text": "Εννοείτε…",
            "payload": {"store_id": 4, "intent": "card_check_in_now"},
        }

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        fake_pending,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *a, **k: None)
    monkeypatch.setattr(
        "app.repo_telegram_assistant.create_task",
        lambda **kwargs: 900,
    )

    contexts = [
        {"store_id": 4, "store_name": "Training Room Ίλιον", "employer_afm": "1", "branch_aa": "0", "recipient_id": 8},
        {"store_id": 9, "store_name": "ERATO", "employer_afm": "2", "branch_aa": "0", "recipient_id": 36},
    ]

    monkeypatch.setattr(
        "app.telegram_assistant_service.parse_command",
        lambda **kwargs: (
            {
                "intent": "today_info",
                "store_id": 9,
                "employee_afms": [],
                "clarification_question": "Στο ERATO ανοιχτές: …",
                "confidence": 1.0,
            },
            [],
            {},
        ),
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.validate_and_describe",
        lambda *a, **k: ("answered", {"valid": True, "errors": [], "execution_enabled": False}, "Στο ERATO ανοιχτές: …"),
    )

    result = process_assistant_command(
        text="Στο Ερατο ποιες κάρτες είναι ανοιχτές",
        contexts=contexts,
        inbound_id=200,
        chat_id="6809632515",
        confirmation_mode="pin",
    )

    assert calls and calls[0].get("chat_id") == "6809632515"
    assert result["task_id"] == 900
    assert result["status"] == "answered"
    assert "ERATO" in result["answer"]


def test_multi_store_asks_list_when_message_has_no_store(monkeypatch):
    created: dict = {}

    def fake_create(**kwargs):
        created.update(kwargs)
        return 501

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *a, **k: None)
    monkeypatch.setattr("app.repo_telegram_assistant.create_task", fake_create)

    def boom(**kwargs):
        raise AssertionError("LLM must not run before store choice")

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", boom)

    contexts = [
        {"store_id": 4, "store_name": "Training Room Ίλιον", "employer_afm": "1", "branch_aa": "0", "recipient_id": 8},
        {"store_id": 9, "store_name": "ERATO", "employer_afm": "2", "branch_aa": "0", "recipient_id": 36},
    ]
    result = process_assistant_command(
        text="ποιοι εργάζονται ακόμα",
        contexts=contexts,
        inbound_id=201,
        chat_id="6809632515",
        confirmation_mode="pin",
    )
    assert result["status"] == "needs_clarification"
    assert "Επιλέξτε κατάστημα" in result["answer"]
    assert "1. Training Room" in result["answer"]
    assert "2. ERATO" in result["answer"]
    assert created["parsed"]["clarification_kind"] == "store_choice"
    assert created["parsed"]["original_message"] == "ποιοι εργάζονται ακόμα"
    assert created["store_id"] is None


def test_store_choice_reply_replays_original_message(monkeypatch):
    updated: dict = {}
    pending = {
        "id": 77,
        "store_id": None,
        "recipient_id": None,
        "task_status": "needs_clarification",
        "proposed_action_text": "Επιλέξτε κατάστημα…",
        "original_message_text": "ποιοι εργάζονται ακόμα",
        "payload": {
            "clarification_kind": "store_choice",
            "original_message": "ποιοι εργάζονται ακόμα",
            "candidate_store_ids": [4, 9],
            "intent": "unknown",
            "employee_afms": [],
        },
    }

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: pending,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *a, **k: None)

    def fake_update(task_id, **kwargs):
        updated["task_id"] = task_id
        updated.update(kwargs)
        return True

    monkeypatch.setattr("app.repo_telegram_assistant.update_assistant_task", fake_update)

    def fake_parse(**kwargs):
        assert kwargs["text"] == "ποιοι εργάζονται ακόμα"
        assert kwargs["reply_context"]["store_id"] == 9
        return (
            {
                "intent": "today_info",
                "store_id": 9,
                "employee_afms": [],
                "clarification_question": "Στο ERATO: HOXHA",
                "confidence": 1.0,
            },
            [],
            {"llm_used": "gemini"},
        )

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", fake_parse)
    monkeypatch.setattr(
        "app.telegram_assistant_service.validate_and_describe",
        lambda *a, **k: (
            "answered",
            {"valid": True, "errors": [], "execution_enabled": False},
            "Στο ERATO: HOXHA",
        ),
    )

    contexts = [
        {"store_id": 4, "store_name": "Training Room Ίλιον", "employer_afm": "1", "branch_aa": "0", "recipient_id": 8},
        {"store_id": 9, "store_name": "ERATO", "employer_afm": "2", "branch_aa": "0", "recipient_id": 36},
    ]
    result = process_assistant_command(
        text="2",
        contexts=contexts,
        inbound_id=202,
        chat_id="6809632515",
        confirmation_mode="pin",
    )
    assert result["status"] == "answered"
    assert result["task_id"] == 77
    assert result["parsed"]["store_id"] == 9
    assert result["recipient_id"] == 36
    assert updated["task_id"] == 77
    assert updated["recipient_id"] == 36


def test_mentioned_store_proceeds_without_list(monkeypatch):
    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *a, **k: None)
    monkeypatch.setattr("app.repo_telegram_assistant.create_task", lambda **kwargs: 910)

    def fake_parse(**kwargs):
        assert kwargs["reply_context"]["store_id"] == 9
        return (
            {
                "intent": "today_info",
                "store_id": 9,
                "employee_afms": [],
                "clarification_question": "ok",
                "confidence": 1.0,
            },
            [],
            {},
        )

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", fake_parse)
    monkeypatch.setattr(
        "app.telegram_assistant_service.validate_and_describe",
        lambda *a, **k: ("answered", {"valid": True, "errors": [], "execution_enabled": False}, "ok"),
    )
    contexts = [
        {"store_id": 4, "store_name": "Training Room Ίλιον", "employer_afm": "1", "branch_aa": "0", "recipient_id": 8},
        {"store_id": 9, "store_name": "ERATO", "employer_afm": "2", "branch_aa": "0", "recipient_id": 36},
    ]
    result = process_assistant_command(
        text="Στο Ερατο ποιοι εργάζονται ακόμα",
        contexts=contexts,
        inbound_id=203,
        chat_id="1",
        confirmation_mode="pin",
    )
    assert result["status"] == "answered"
    assert result["task_id"] == 910


def test_mentioned_store_beats_conversation_focus_for_today_home(monkeypatch):
    from app.telegram_assistant_service import parse_command

    captured = {}

    class _Resp:
        ok = True
        status_code = 200

        def json(self):
            return {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": (
                                '{"intent":"today_info","store_id":9,"employee_afms":[],'
                                '"clarification_question":"ok","confidence":1}'
                            )
                        }]
                    }
                }]
            }

    def fake_post(_url, **kwargs):
        body = kwargs.get("json") or {}
        parts = (((body.get("contents") or [{}])[0]).get("parts") or [{}])
        prompt = json.loads(parts[0].get("text") or "{}")
        captured["today_home"] = prompt.get("today_home")
        return _Resp()

    monkeypatch.setattr("app.telegram_assistant_service.requests.post", fake_post)
    monkeypatch.setattr(
        "app.telegram_assistant_service.build_today_home_context",
        lambda contexts: {
            "date": "2026-08-20",
            "stores": [
                {"store_id": 4, "name": "Training Room", "employees": [{"afm": "1"}]},
                {"store_id": 9, "name": "ERATO", "employees": [{"afm": "2"}]},
            ],
        },
    )
    monkeypatch.setattr("app.telegram_assistant_service.Config.GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda contexts: [
            {"store_id": 4, "afm": "1", "name": "A"},
            {"store_id": 9, "afm": "2", "name": "B"},
        ],
    )

    contexts = [
        {"store_id": 4, "store_name": "Training Room Ίλιον", "employer_afm": "1", "branch_aa": "0"},
        {"store_id": 9, "store_name": "ERATO", "employer_afm": "2", "branch_aa": "0"},
    ]
    parse_command(
        text="Στο Ερατο ποιοι εργάζονται ακόμα",
        contexts=contexts,
        reply_context={"store_id": 4, "employee_afm": "1"},
    )
    stores = (captured.get("today_home") or {}).get("stores") or []
    assert [int(s["store_id"]) for s in stores] == [9]


def test_erato_greek_matches_latin_store_name():
    from app.telegram_assistant_service import _mentioned_store_ids

    contexts = [
        {"store_id": 4, "store_name": "Training Room Ίλιον"},
        {"store_id": 9, "store_name": "ERATO"},
    ]
    assert _mentioned_store_ids("Στο Ερατο ποιες κάρτες", contexts) == [9]
    assert _mentioned_store_ids("Στο Ερατοσθένους ανοιχτές", contexts) == [9]

def test_yes_to_cancel_clarification_closes_same_task(monkeypatch):
    pending = {
        "id": 51,
        "recipient_id": None,
        "store_id": 4,
        "task_status": "needs_clarification",
        "clarification_text": (
            "Η εντολή #51 χρειάζεται διευκρίνιση:\n"
            "• Θα θέλατε να ακυρώσω την εντολή για τους εργαζομένους DRAME BABACAR και RANA MD-MASUD;"
        ),
        "payload": {"store_id": 4, "employee_afms": ["111", "222"]},
    }
    cancelled = {}

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: pending,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.cancel_assistant_task",
        lambda task_id, reason="user_cancelled": cancelled.update({"id": task_id, "reason": reason}) or True,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)

    def boom(*args, **kwargs):
        raise AssertionError("Gemini must not run for yes-to-cancel")

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", boom)

    result = process_assistant_command(
        text="ναι",
        contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
        inbound_id=99,
        store_id=4,
        confirmation_mode="ui",
        office_user="admin",
    )
    assert result["task_id"] == 51
    assert result["status"] == "answered"
    assert result["task_status"] == "cancelled"
    assert result["reset_conversation_focus"] is True
    assert result["parsed"].get("employee_afms") == []
    assert "Ακυρώθηκε η εντολή #51" in result["answer"]
    assert cancelled["id"] == 51


def test_gemini_cancel_pending_aborts_open_clarification(monkeypatch):
    """Any dismissive phrasing → Gemini cancel_pending → same task cancelled."""
    pending = {
        "id": 52,
        "recipient_id": None,
        "store_id": 4,
        "task_status": "needs_clarification",
        "clarification_text": "Εννοείτε του Διονυσιου ή του Κωνσταντινου;",
        "payload": {
            "intent": "card_check_in_now",
            "store_id": 4,
            "ambiguous_employee_afms": ["111", "222"],
        },
    }
    cancelled = {}
    captured = {}

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: pending,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.cancel_assistant_task",
        lambda task_id, reason="user_cancelled": cancelled.update({"id": task_id, "reason": reason}) or True,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda contexts: [],
    )

    def fake_parse(*, text, contexts, reply_context):
        captured["text"] = text
        return (
            {
                "intent": "cancel_pending",
                "store_id": 4,
                "employee_afms": [],
                "date": None,
                "confidence": 0.9,
                "clarification_question": "Ακυρώθηκε η εντολή.",
            },
            [],
            {},
        )

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", fake_parse)

    result = process_assistant_command(
        text="γαμα το μην το κανεις",
        contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
        inbound_id=103,
        store_id=4,
        confirmation_mode="ui",
        office_user="admin",
    )
    assert captured["text"] == "γαμα το μην το κανεις"
    assert result["task_id"] == 52
    assert result["task_status"] == "cancelled"
    assert result["reset_conversation_focus"] is True
    assert result["parsed"].get("employee_afms") == []
    assert "Ακυρώθηκε η εντολή #52" in result["answer"]
    assert "Εννοείτε" not in result["answer"]
    assert cancelled["id"] == 52


def test_cancel_pending_without_clarification_clears_focus(monkeypatch):
    """«Άκυρο» on a draft (no clarification) cancels opens and restarts conversation."""
    cancelled_open = {}

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.cancel_open_assistant_tasks",
        lambda **kwargs: cancelled_open.update(kwargs) or [88],
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.telegram_assistant_service.parse_command",
        lambda **kwargs: (
            {"intent": "cancel_pending", "employee_afms": [], "store_id": 4, "confidence": 1.0},
            [],
            {},
        ),
    )

    result = process_assistant_command(
        text="άκυρο",
        contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
        inbound_id=200,
        store_id=4,
        confirmation_mode="ui",
        office_user="admin",
    )
    assert cancelled_open.get("office_user") == "admin"
    assert cancelled_open.get("store_id") == 4
    assert result["task_id"] == 88
    assert result["task_status"] == "cancelled"
    assert result["reset_conversation_focus"] is True
    assert result["parsed"].get("employee_afms") == []
    assert "Ακυρώθηκε η εντολή #88" in result["answer"]


def test_cancel_pending_cites_newest_open_task(monkeypatch):
    """If several opens exist, the reply cites the newest id first (not a leftover old one)."""
    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.cancel_open_assistant_tasks",
        lambda **kwargs: [60, 50],
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.telegram_assistant_service.parse_command",
        lambda **kwargs: (
            {"intent": "cancel_pending", "employee_afms": [], "store_id": 4, "confidence": 1.0},
            [],
            {},
        ),
    )

    result = process_assistant_command(
        text="ακυρο",
        contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
        inbound_id=201,
        store_id=4,
        confirmation_mode="ui",
        office_user="admin",
    )
    assert result["task_id"] == 60
    assert "#60" in result["answer"]
    assert result["answer"].index("#60") < result["answer"].index("#50")
    assert "Ακυρώθηκαν οι ανοιχτές εντολές #60, #50" in result["answer"]


def test_followup_answer_updates_same_clarification_task(monkeypatch):
    pending = {
        "id": 52,
        "recipient_id": None,
        "store_id": 4,
        "task_status": "needs_clarification",
        "clarification_text": "Παρακαλώ διευκρινίστε ποια ενέργεια θέλετε.",
        "payload": {"store_id": 4, "employee_afms": ["111", "222"]},
    }
    updates = {}
    captured = {}

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: pending,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.update_assistant_task",
        lambda task_id, **kwargs: updates.update({"id": task_id, **kwargs}) or True,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)

    def fake_parse(*, text, contexts, reply_context):
        captured["text"] = text
        captured["reply_context"] = reply_context
        return (
            {
                "intent": "card_check_out_now",
                "store_id": 4,
                "employee_afms": ["111", "222"],
                "date": "2026-08-20",
                "confidence": 0.9,
            },
            [{"store_id": 4, "afm": "111", "name": "A"}, {"store_id": 4, "afm": "222", "name": "B"}],
            {},
        )

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", fake_parse)
    monkeypatch.setattr(
        "app.telegram_assistant_service.validate_and_describe",
        lambda *args, **kwargs: (
            "draft",
            {"valid": True, "errors": [], "execution_enabled": True},
            "A, B · 20/08/2026 · Κλείσιμο κάρτας τώρα",
        ),
    )

    result = process_assistant_command(
        text="κλείσε κάρτα τώρα",
        contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
        inbound_id=100,
        store_id=4,
        confirmation_mode="ui",
        office_user="admin",
    )
    assert captured["text"] == "κλείσε κάρτα τώρα"
    assert result["task_id"] == 52
    assert updates["id"] == 52
    assert updates["status"] == "awaiting_ui_confirmation"
    assert result["answer"].startswith("Εντολή #52:")


def test_name_choice_answer_sent_as_is_to_gemini(monkeypatch):
    """Raw answers like «διονυση» / greeklish go to Gemini with name_choice context."""
    employees = [
        {"afm": "111111111", "name": "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ", "store_id": 4},
        {"afm": "222222222", "name": "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ", "store_id": 4},
    ]
    pending = {
        "id": 52,
        "recipient_id": None,
        "store_id": 4,
        "task_status": "needs_clarification",
        "clarification_text": (
            "Η εντολή #52 χρειάζεται διευκρίνιση:\n"
            "• Εννοείτε του Διονυσιου ή του Κωνσταντινου;\n\n"
            "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
        ),
        "original_message_text": "Κλείσε του Φωτόπουλου",
        "payload": {
            "intent": "card_check_in_now",
            "store_id": 4,
            "employee_afms": [],
            "ambiguous_employee_afms": ["111111111", "222222222"],
            "date": "2026-08-20",
            "confidence": 0.9,
        },
    }
    updates = {}
    captured = {}

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: pending,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.update_assistant_task",
        lambda task_id, **kwargs: updates.update({"id": task_id, **kwargs}) or True,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda contexts: employees,
    )

    def fake_parse(*, text, contexts, reply_context):
        captured["text"] = text
        captured["pending"] = (reply_context or {}).get("pending_clarification")
        return (
            {
                "intent": "card_check_in_now",
                "store_id": 4,
                "employee_afms": ["222222222"],
                "date": "2026-08-20",
                "confidence": 0.95,
            },
            employees,
            {"model": "test"},
        )

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", fake_parse)

    from unittest.mock import patch

    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        result = process_assistant_command(
            text="διονυση",
            contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
            inbound_id=101,
            store_id=4,
            confirmation_mode="ui",
            office_user="admin",
        )

    assert captured["text"] == "διονυση"
    assert captured["pending"]["kind"] == "name_choice"
    assert captured["pending"]["original_message"] == "Κλείσε του Φωτόπουλου"
    assert set(captured["pending"]["candidate_afms"]) == {"111111111", "222222222"}
    assert result["task_id"] == 52
    assert result["status"] == "draft"
    assert updates["parsed"]["employee_afms"] == ["222222222"]
    assert "Εννοείτε" not in result["answer"]


def test_name_ambiguity_keeps_original_command_until_choice(monkeypatch):
    """A missing employee choice must not turn the existing action into unknown."""
    from unittest.mock import patch

    from app.telegram_assistant_service import validate_and_describe

    employees = [
        {"afm": "111111111", "name": "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ", "store_id": 4},
        {"afm": "222222222", "name": "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ", "store_id": 4},
    ]
    parsed = {
        "intent": "card_check_out_now",
        "pending_intent": "card_check_out_now",
        "store_id": 4,
        "employee_afms": [],
        "ambiguous_employee_afms": ["111111111", "222222222"],
        "date": "2026-08-20",
        "confidence": 0.95,
        "clarification_question": (
            "Εννοείτε του Φωτόπουλου Διονύσιου ή του Φωτόπουλου Κωνσταντίνου;"
        ),
    }

    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, _ = validate_and_describe(
            parsed,
            contexts=[{
                "store_id": 4,
                "store_name": "ERATO",
                "employer_afm": "1",
                "branch_aa": "0",
            }],
            employees=employees,
            user_text="Κλείσε του Φωτόπουλου",
        )

    assert status == "needs_clarification"
    assert validation["errors"] == [parsed["clarification_question"]]
    assert parsed["intent"] == "card_check_out_now"
    assert parsed["pending_intent"] == "card_check_out_now"
    assert parsed["ambiguous_employee_afms"] == ["111111111", "222222222"]


def test_unknown_name_ambiguity_promotes_pending_intent(monkeypatch):
    """Compatibility: pending_intent restores the action if Gemini says unknown."""
    from app.telegram_assistant_service import validate_and_describe

    employees = [
        {"afm": "111111111", "name": "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ", "store_id": 4},
        {"afm": "222222222", "name": "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ", "store_id": 4},
    ]
    parsed = {
        "intent": "unknown",
        "pending_intent": "card_check_out_now",
        "store_id": 4,
        "employee_afms": [],
        "ambiguous_employee_afms": ["111111111", "222222222"],
        "date": "2026-08-20",
        "confidence": 0.9,
        "clarification_question": "Εννοείτε του Διονύσιου ή του Κωνσταντίνου;",
    }

    status, _, _ = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        employees=employees,
        user_text="Κλείσε του Φωτόπουλου",
    )

    assert status == "needs_clarification"
    assert parsed["intent"] == "card_check_out_now"


def test_reply_to_confirmation_revises_same_open_task(monkeypatch):
    """Until execution/cancellation, a reply updates the current command, not a new one."""
    pending = {
        "id": 64,
        "recipient_id": None,
        "store_id": 4,
        "task_status": "awaiting_ui_confirmation",
        "proposed_action_text": "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ · Κλείσιμο κάρτας τώρα",
        "original_message_text": "Κλείσε του Κωνσταντίνου",
        "payload": {
            "intent": "card_check_out_now",
            "store_id": 4,
            "employee_afms": ["111111111"],
            "date": "2026-08-20",
        },
    }
    updates = {}

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification", lambda **kwargs: pending,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.update_assistant_task",
        lambda task_id, **kwargs: updates.update({"id": task_id, **kwargs}) or True,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.telegram_assistant_service.parse_command",
        lambda **kwargs: (
            {
                "intent": "card_check_out_retro",
                "store_id": 4,
                "employee_afms": [],
                "date": "2026-08-20",
                "time": "17:00",
                "confidence": 0.95,
            },
            [{"store_id": 4, "afm": "111111111", "name": "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ"}],
            {},
        ),
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.validate_and_describe",
        lambda parsed, **kwargs: (
            "draft",
            {"valid": True, "errors": [], "execution_enabled": True},
            "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ · Κλείσιμο κάρτας στις 17:00",
        ),
    )

    result = process_assistant_command(
        text="όχι τώρα, στις 17:00",
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        inbound_id=501,
        store_id=4,
        confirmation_mode="ui",
        office_user="admin",
    )

    assert result["task_id"] == 64
    assert updates["id"] == 64
    assert updates["status"] == "awaiting_ui_confirmation"
    assert updates["parsed"]["employee_afms"] == ["111111111"]
    assert updates["parsed"]["time"] == "17:00"


def test_name_choice_greeklish_answer_uses_gemini(monkeypatch):
    employees = [
        {"afm": "111111111", "name": "ΦΩΤΟΠΟΥΛΟΣ ΚΩΝΣΤΑΝΤΙΝΟΣ", "store_id": 4},
        {"afm": "222222222", "name": "ΦΩΤΟΠΟΥΛΟΣ ΔΙΟΝΥΣΙΟΣ", "store_id": 4},
    ]
    pending = {
        "id": 52,
        "recipient_id": None,
        "store_id": 4,
        "task_status": "needs_clarification",
        "clarification_text": "Εννοείτε του Διονυσιου ή του Κωνσταντινου;",
        "payload": {
            "intent": "card_check_in_now",
            "store_id": 4,
            "ambiguous_employee_afms": ["111111111", "222222222"],
            "date": "2026-08-20",
        },
    }
    updates = {}
    captured = {}

    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        lambda **kwargs: pending,
    )
    monkeypatch.setattr(
        "app.repo_telegram_assistant.update_assistant_task",
        lambda task_id, **kwargs: updates.update({"id": task_id, **kwargs}) or True,
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda contexts: employees,
    )

    def fake_parse(*, text, contexts, reply_context):
        captured["text"] = text
        return (
            {
                "intent": "unknown",
                "store_id": None,
                "employee_afms": ["222222222"],
                "date": None,
                "confidence": 0.8,
            },
            employees,
            {},
        )

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", fake_parse)

    from unittest.mock import patch

    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        result = process_assistant_command(
            text="dionisi",
            contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
            inbound_id=102,
            store_id=4,
            confirmation_mode="ui",
            office_user="admin",
        )

    assert captured["text"] == "dionisi"
    # preserve_* fills intent/date when Gemini returns unknown/empty
    assert updates["parsed"]["intent"] == "card_check_in_now"
    assert updates["parsed"]["date"] == "2026-08-20"
    assert result["status"] == "draft"
    assert updates["parsed"]["employee_afms"] == ["222222222"]


def test_is_cancel_command_phrases():
    from app.assistant_conversation_service import _is_cancel_command

    assert _is_cancel_command("άκυρο")
    assert _is_cancel_command("ΑΚΥΡΟ!")
    assert _is_cancel_command("ακύρωσε")
    assert _is_cancel_command("cancel")
    assert not _is_cancel_command("άνοιξε κάρτα")
    assert not _is_cancel_command("στο Ερατο ποιοι δουλεύουν")


def test_akyro_cancels_without_gemini(monkeypatch):
    """«άκυρο» δεν καλεί Gemini — ακυρώνει ανοιχτές τοπικά."""
    monkeypatch.setattr(
        "app.repo_telegram_assistant.cancel_open_assistant_tasks",
        lambda **kwargs: [55],
    )
    monkeypatch.setattr("app.repo_telegram_assistant.mark_inbound", lambda *a, **k: None)

    def boom(*_a, **_k):
        raise AssertionError("Gemini must not be called for άκυρο")

    monkeypatch.setattr("app.telegram_assistant_service.parse_command", boom)
    monkeypatch.setattr(
        "app.repo_telegram_assistant.latest_pending_clarification",
        boom,
    )

    result = process_assistant_command(
        text="άκυρο",
        contexts=[{
            "store_id": 9,
            "store_name": "ERATO",
            "employer_afm": "091065232",
            "branch_aa": "0",
        }],
        inbound_id=301,
        chat_id="6809632515",
        confirmation_mode="pin",
    )
    assert result["status"] == "answered"
    assert result["task_status"] == "cancelled"
    assert result["task_id"] == 55
    assert result["reset_conversation_focus"] is True
    assert "Ακυρώθηκε" in result["answer"]
