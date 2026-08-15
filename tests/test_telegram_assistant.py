from unittest.mock import patch

from flask import Flask

from app.routes_telegram import telegram_bp
from app.telegram_assistant_service import validate_and_describe


def _app():
    app = Flask(__name__)
    app.register_blueprint(telegram_bp)
    return app


def test_unknown_chat_is_silently_ignored():
    payload = {"update_id": 10, "message": {"message_id": 20, "chat": {"id": 999}, "text": "άνοιξε κάρτα τώρα"}}
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=[]), \
         patch("app.routes_telegram._reply_chat") as reply:
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    reply.assert_not_called()


def test_authorized_message_creates_dry_run_task_only():
    payload = {"update_id": 11, "message": {"message_id": 21, "chat": {"id": 123}, "text": "άνοιξε κάρτα τώρα"}}
    contexts = [{
        "recipient_id": 7, "store_id": 4, "store_name": "ERATO",
        "employer_afm": "123456789", "branch_aa": "0",
    }]
    parsed = {
        "intent": "card_check_in_now", "store_id": 4,
        "employee_afm": "111222333", "date": "2026-08-15", "confidence": 0.99,
    }
    employees = [{"store_id": 4, "afm": "111222333", "name": "ΔΟΚΙΜΗ ΧΡΗΣΤΗΣ"}]
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(31, True)), \
         patch("app.repo_telegram_assistant.reply_context", return_value=None), \
         patch("app.repo_telegram_assistant.create_task", return_value=41) as create_task, \
         patch("app.repo_telegram_assistant.mark_inbound") as mark, \
         patch("app.telegram_assistant_service.parse_command", return_value=(parsed, employees)), \
         patch("app.routes_telegram._reply_chat") as reply, \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert create_task.call_args.kwargs["status"] == "awaiting_confirmation"
    assert create_task.call_args.kwargs["validation"]["execution_enabled"] is False
    assert "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ" in reply.call_args.args[1]
    assert "Είστε σύμφωνοι; Απαντήστε ΝΑΙ ή ΟΧΙ" in reply.call_args.args[1]
    assert reply.call_args.kwargs["context"]["notification_type"] == "assistant_confirmation"
    mark.assert_called_with(31, "parsed")


def test_yes_moves_pending_task_to_pin_step_without_gemini():
    payload = {"update_id": 13, "message": {"message_id": 23, "chat": {"id": 123}, "text": "ΝΑΙ"}}
    contexts = [{"recipient_id": 7, "store_id": 4, "store_name": "ERATO"}]
    conversation = {
        "id": 41, "recipient_id": 7, "store_id": 4,
        "task_status": "awaiting_confirmation", "proposed_action_text": "Άνοιγμα καρτών",
    }
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.conversation_task", return_value=conversation), \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(33, True)), \
         patch("app.repo_telegram_assistant.transition_task", return_value=True) as transition, \
         patch("app.repo_telegram_assistant.mark_inbound") as mark, \
         patch("app.telegram_assistant_service.parse_command") as parse, \
         patch("app.routes_telegram._reply_chat") as reply, \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.get_json()["assistant"] == "awaiting_pin"
    transition.assert_called_once_with(
        41, expected_status="awaiting_confirmation", new_status="awaiting_pin",
        event_type="recipient_accepted",
    )
    parse.assert_not_called()
    assert "4ψήφιο PIN" in reply.call_args.args[1]
    assert reply.call_args.kwargs["context"]["notification_type"] == "assistant_pin"
    mark.assert_called_once_with(33, "conversation")


def test_correct_pin_is_redacted_and_confirms_dry_run_without_gemini():
    payload = {"update_id": 14, "message": {"message_id": 24, "chat": {"id": 123}, "text": "1234"}}
    contexts = [{"recipient_id": 7, "store_id": 4, "store_name": "ERATO"}]
    conversation = {
        "id": 41, "recipient_id": 7, "store_id": 4,
        "task_status": "awaiting_pin", "proposed_action_text": "Άνοιγμα καρτών · ΒΗΧΟΥ, HOXHA",
    }
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.conversation_task", return_value=conversation), \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(34, True)) as create_inbound, \
         patch("app.repo_telegram_assistant.verify_and_confirm_task_pin", return_value=("confirmed", conversation)) as verify, \
         patch("app.repo_telegram_assistant.mark_inbound"), \
         patch("app.telegram_assistant_service.parse_command") as parse, \
         patch("app.routes_telegram._reply_chat") as reply, \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.get_json()["assistant"] == "confirmed_dry_run"
    assert create_inbound.call_args.kwargs["text"] == "[REDACTED_PIN]"
    assert create_inbound.call_args.kwargs["raw_payload"]["message"]["text"] == "[REDACTED_PIN]"
    verify.assert_called_once_with(41, chat_id="123", pin="1234")
    parse.assert_not_called()
    assert "ΘΑ εκτελεστεί" in reply.call_args.args[1]
    assert "ΒΗΧΟΥ, HOXHA" in reply.call_args.args[1]


def test_no_cancels_pending_task_without_gemini():
    payload = {"update_id": 15, "message": {"message_id": 25, "chat": {"id": 123}, "text": "όχι"}}
    contexts = [{"recipient_id": 7, "store_id": 4, "store_name": "ERATO"}]
    conversation = {"id": 41, "recipient_id": 7, "store_id": 4, "task_status": "awaiting_confirmation"}
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.conversation_task", return_value=conversation), \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(35, True)), \
         patch("app.repo_telegram_assistant.transition_task", return_value=True) as transition, \
         patch("app.repo_telegram_assistant.mark_inbound"), \
         patch("app.telegram_assistant_service.parse_command") as parse, \
         patch("app.routes_telegram._reply_chat"), \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.get_json()["assistant"] == "cancelled"
    transition.assert_called_once_with(
        41, expected_status="awaiting_confirmation", new_status="cancelled",
        event_type="cancelled_by_recipient",
    )
    parse.assert_not_called()


def test_duplicate_update_is_not_parsed_or_answered_again():
    payload = {"update_id": 11, "message": {"message_id": 21, "chat": {"id": 123}, "text": "άνοιξε κάρτα τώρα"}}
    contexts = [{
        "recipient_id": 7, "store_id": 4, "store_name": "ERATO",
        "employer_afm": "123456789", "branch_aa": "0",
    }]
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(31, False)), \
         patch("app.telegram_assistant_service.parse_command") as parse, \
         patch("app.routes_telegram._reply_chat") as reply:
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "duplicate": True}
    parse.assert_not_called()
    reply.assert_not_called()


def test_gemini_failure_is_recorded_without_creating_task():
    payload = {"update_id": 12, "message": {"message_id": 22, "chat": {"id": 123}, "text": "άνοιξε κάρτα τώρα"}}
    contexts = [{
        "recipient_id": 7, "store_id": 4, "store_name": "ERATO",
        "employer_afm": "123456789", "branch_aa": "0",
    }]
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(32, True)), \
         patch("app.repo_telegram_assistant.reply_context", return_value=None), \
         patch("app.repo_telegram_assistant.create_task") as create_task, \
         patch("app.repo_telegram_assistant.mark_inbound") as mark, \
         patch("app.telegram_assistant_service.parse_command", side_effect=RuntimeError("Gemini unavailable")), \
         patch("app.routes_telegram._reply_chat") as reply, \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    create_task.assert_not_called()
    mark.assert_called_once_with(32, "failed", "Gemini unavailable")
    assert "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ" in reply.call_args.args[1]


def test_schedule_change_validation_and_description():
    parsed = {
        "intent": "schedule_change", "store_id": 4, "employee_afm": "111222333",
        "date": "2026-08-16", "hour_from": "09:00", "hour_to": "17:00",
    }
    status, validation, proposed = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        employees=[{"store_id": 4, "afm": "111222333", "name": "ΔΟΚΙΜΗ ΧΡΗΣΤΗΣ"}],
    )
    assert status == "draft"
    assert validation == {"valid": True, "errors": [], "execution_enabled": False}
    assert "09:00–17:00" in proposed
    assert "ERATO" in proposed


def test_multiple_employees_are_validated_and_described_together():
    parsed = {
        "intent": "card_check_in_retro", "store_id": 4,
        "employee_afms": ["111222333", "444555666"],
        "employee_references": ["Βήχου", "Hoxha"],
        "date": "2026-08-15", "time": "09:50",
    }
    status, validation, proposed = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        employees=[
            {"store_id": 4, "afm": "111222333", "name": "ΒΗΧΟΥ ΜΑΡΙΑ"},
            {"store_id": 4, "afm": "444555666", "name": "HOXHA ARBEN"},
        ],
    )
    assert status == "draft"
    assert validation["valid"] is True
    assert parsed["employee_afms"] == ["111222333", "444555666"]
    assert parsed["employee_afm"] is None
    assert "ΒΗΧΟΥ ΜΑΡΙΑ, HOXHA ARBEN" in proposed
    assert "στις 09:50" in proposed


def test_multiple_employees_require_every_afm_to_be_authorized():
    parsed = {
        "intent": "card_check_in_retro", "store_id": 4,
        "employee_afms": ["111222333", "999999999"],
        "employee_references": ["Βήχου", "Άγνωστος"],
        "date": "2026-08-15", "time": "09:50",
    }
    status, validation, _ = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        employees=[{"store_id": 4, "afm": "111222333", "name": "ΒΗΧΟΥ ΜΑΡΙΑ"}],
    )
    assert status == "needs_clarification"
    assert validation["valid"] is False
    assert "Δεν προσδιορίστηκαν μοναδικά όλοι οι εργαζόμενοι του καταστήματος" in validation["errors"]


def test_impossible_calendar_date_needs_clarification():
    parsed = {
        "intent": "rest_day", "store_id": 4, "employee_afm": "111222333",
        "date": "2026-02-30",
    }
    status, validation, _ = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        employees=[{"store_id": 4, "afm": "111222333", "name": "ΔΟΚΙΜΗ ΧΡΗΣΤΗΣ"}],
    )
    assert status == "needs_clarification"
    assert validation["valid"] is False
    assert "Δεν προσδιορίστηκε έγκυρη ημερομηνία" in validation["errors"]
