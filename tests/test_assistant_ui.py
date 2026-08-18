from unittest.mock import patch

from flask import Flask, session

from app.routes_assistant import assistant_bp


def _app():
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(assistant_bp)
    return app


def _login(client):
    with client.session_transaction() as sess:
        sess["office_user"] = "admin"
        sess["office_logged_in"] = True


def test_disabled_store_rejects_ui_message_before_ai():
    client = _app().test_client(); _login(client)
    store = {"id": 4, "name": "ERATO", "employer_afm": "123", "branch_aa": "0"}
    with patch("app.routes_assistant.can_access_store", return_value=True), \
         patch("app.routes_assistant.get_store_config", return_value=store), \
         patch("app.routes_assistant.get_action_settings", return_value={"ai_agent_enabled": False}), \
         patch("app.repo_telegram_assistant.create_ui_inbound_message", return_value=31) as inbound, \
         patch("app.repo_telegram_assistant.record_ui_outbound_message") as outbound, \
         patch("app.repo_telegram_assistant.mark_inbound") as mark, \
         patch("app.routes_assistant.record_audit_event"), \
         patch("app.assistant_conversation_service.process_assistant_command") as process:
        response = client.post("/api/assistant/message", json={"store_id": 4, "text": "άνοιξε κάρτα"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["disabled"] is True
    assert "δεν είναι ενεργοποιημένος" in body["answer"]
    inbound.assert_called_once()
    outbound.assert_called_once()
    mark.assert_called_once_with(31, "disabled")
    process.assert_not_called()


def test_ui_message_uses_shared_conversation_service():
    client = _app().test_client(); _login(client)
    store = {"id": 4, "name": "ERATO", "employer_afm": "123", "branch_aa": "0"}
    result = {"task_id": 41, "status": "draft", "task_status": "awaiting_ui_confirmation",
              "answer": "Εντολή #41", "parsed": {"store_id": 4}, "validation": {},
              "proposed": "Άνοιγμα κάρτας", "recipient_id": None}
    with patch("app.routes_assistant.can_access_store", return_value=True), \
         patch("app.routes_assistant.get_store_config", return_value=store), \
         patch("app.routes_assistant.get_action_settings", return_value={"ai_agent_enabled": True}), \
         patch("app.repo_telegram_assistant.create_ui_inbound_message", return_value=31), \
         patch("app.repo_telegram_assistant.latest_chat_context", return_value=None), \
         patch("app.assistant_conversation_service.process_assistant_command", return_value=result) as process, \
         patch("app.repo_telegram_assistant.record_ui_outbound_message") as outbound, \
         patch("app.routes_assistant.record_audit_event"):
        response = client.post("/api/assistant/message", json={"store_id": 4, "text": "άνοιξε κάρτα"})
    assert response.status_code == 200
    assert process.call_args.kwargs["confirmation_mode"] == "ui"
    assert process.call_args.kwargs["contexts"][0]["store_id"] == 4
    outbound.assert_called_once()


def test_ui_confirmation_is_scoped_to_user_and_store():
    client = _app().test_client(); _login(client)
    task = {"id": 41, "store_id": 4, "task_status": "executing", "payload_json": "{}"}
    execution = {"success": True, "results": [{"employee": "TEST", "success": True, "protocol": "P-1"}]}
    with patch("app.routes_assistant.can_access_store", return_value=True), \
         patch("app.repo_telegram_assistant.confirm_ui_task", return_value=task) as confirm, \
         patch("app.assistant_execution_service.execute_confirmed_task", return_value=execution) as execute, \
         patch("app.repo_telegram_assistant.record_ui_outbound_message"), \
         patch("app.routes_assistant.record_audit_event"):
        response = client.post("/api/assistant/task/41/confirm", json={"store_id": 4})
    assert response.status_code == 200
    confirm.assert_called_once_with(task_id=41, store_id=4, office_user="admin")
    execute.assert_called_once_with(task, source="assistant_ui")
    assert "Πρωτόκολλο: P-1" in response.get_json()["answer"]


def test_ui_ai_configuration_failure_is_persisted_as_chat_reply():
    client = _app().test_client(); _login(client)
    store = {"id": 4, "name": "ERATO", "employer_afm": "123", "branch_aa": "0"}
    with patch("app.routes_assistant.can_access_store", return_value=True), \
         patch("app.routes_assistant.get_store_config", return_value=store), \
         patch("app.routes_assistant.get_action_settings", return_value={"ai_agent_enabled": True}), \
         patch("app.repo_telegram_assistant.create_ui_inbound_message", return_value=31), \
         patch("app.repo_telegram_assistant.latest_chat_context", return_value=None), \
         patch("app.assistant_conversation_service.process_assistant_command", side_effect=RuntimeError("Δεν έχει ρυθμιστεί GEMINI_API_KEY")), \
         patch("app.repo_telegram_assistant.mark_inbound") as mark, \
         patch("app.repo_telegram_assistant.record_ui_outbound_message") as outbound, \
         patch("app.routes_assistant.record_audit_event"):
        response = client.post("/api/assistant/message", json={"store_id": 4, "text": "άνοιξε κάρτα"})
    assert response.status_code == 500
    assert "GEMINI_API_KEY" in response.get_json()["error"]
    mark.assert_called_once_with(31, "failed", "Δεν έχει ρυθμιστεί GEMINI_API_KEY")
    assert "GEMINI_API_KEY" in outbound.call_args.kwargs["text"]
