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
    assert create_task.call_args.kwargs["status"] == "draft"
    assert create_task.call_args.kwargs["validation"]["execution_enabled"] is False
    assert "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ" in reply.call_args.args[1]
    mark.assert_called_with(31, "parsed")


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
