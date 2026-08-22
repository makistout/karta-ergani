import json
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask, jsonify

from app.assistant_execution_service import execute_confirmed_task, execution_answer


def test_confirmed_schedule_card_submits_real_time_and_returns_protocol():
    app = Flask(__name__)
    task = {
        "id": 8, "store_id": 4,
        "payload_json": json.dumps({
            "intent": "card_check_in_schedule", "store_id": 4,
            "employee_afms": ["111222333"], "date": "2026-08-17",
            "resolved_schedule_times": {"111222333": "09:00"},
        }),
    }
    store = {"id": 4, "employer_afm": "123456789", "branch_aa": "0"}
    employee = {"afm": "111222333", "eponymo": "HOXHA", "onoma": "DASHURI"}
    client = SimpleNamespace(base_url="https://example.invalid/")
    with app.app_context(), \
         patch("app.assistant_execution_service.get_store_config", return_value=store), \
         patch("app.assistant_execution_service.get_action_settings", return_value={"ai_agent_enabled": True}), \
         patch("app.assistant_execution_service._authenticate", return_value=("token", client)), \
         patch("app.assistant_execution_service._employees", return_value=[employee]), \
         patch("app.routes_work_card._submit_work_card", return_value=(
             jsonify({"success": True, "protocol": "P-123"}), 200,
         )) as submit, \
         patch("app.repo_telegram_assistant.finish_task_execution") as finish:
        result = execute_confirmed_task(task, source="assistant_ui")

    assert result["success"] is True
    assert result["results"][0]["protocol"] == "P-123"
    body = submit.call_args.kwargs["body"]
    assert body["event"] == "check_in"
    assert body["event_at"] == "2026-08-17T09:00:00"
    assert body["batch_index"] == 1
    assert body["batch_total"] == 1
    finish.assert_called_once_with(8, success=True, result=result)
    assert execution_answer(8, result) == "Εντολή #8:\nHOXHA DASHURI · Επιτυχία · Πρωτόκολλο: P-123"


def test_execution_stops_if_store_ai_was_disabled_after_parsing():
    task = {"id": 9, "store_id": 4, "payload_json": "{}"}
    with patch("app.assistant_execution_service.get_store_config", return_value={"id": 4}), \
         patch("app.assistant_execution_service.get_action_settings", return_value={"ai_agent_enabled": False}), \
         patch("app.assistant_execution_service._authenticate") as authenticate, \
         patch("app.repo_telegram_assistant.finish_task_execution") as finish:
        result = execute_confirmed_task(task, source="assistant_ui")
    assert result["success"] is False
    authenticate.assert_not_called()
    finish.assert_called_once_with(9, success=False, result=result)


def test_batch_card_punches_use_global_batch_indices():
    app = Flask(__name__)
    task = {
        "id": 11, "store_id": 4,
        "payload_json": json.dumps({
            "store_id": 4,
            "commands": [
                {"intent": "card_check_in_now", "store_id": 4, "employee_afms": ["111"], "date": "2026-08-22"},
                {"intent": "card_check_in_now", "store_id": 4, "employee_afms": ["222"], "date": "2026-08-22"},
            ],
        }),
    }
    store = {"id": 4, "employer_afm": "123456789", "branch_aa": "0"}
    employees_by_afm = {
        "111": {"afm": "111", "eponymo": "A", "onoma": "ONE"},
        "222": {"afm": "222", "eponymo": "B", "onoma": "TWO"},
    }
    client = SimpleNamespace(base_url="https://example.invalid/")

    def fake_employees(_store, afms):
        return [employees_by_afm[afm] for afm in afms]

    with app.app_context(), \
         patch("app.assistant_execution_service.get_store_config", return_value=store), \
         patch("app.assistant_execution_service.get_action_settings", return_value={"ai_agent_enabled": True}), \
         patch("app.assistant_execution_service._authenticate", return_value=("token", client)), \
         patch("app.assistant_execution_service._employees", side_effect=fake_employees), \
         patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None), \
         patch("app.routes_work_card._submit_work_card", return_value=(
             jsonify({"success": True, "protocol": "P-1"}), 200,
         )) as submit, \
         patch("app.repo_telegram_assistant.finish_task_execution"):
        result = execute_confirmed_task(task, source="assistant_telegram")

    assert result["success"] is True
    assert submit.call_count == 2
    first_body = submit.call_args_list[0].kwargs["body"]
    second_body = submit.call_args_list[1].kwargs["body"]
    assert first_body["batch_index"] == 1
    assert second_body["batch_index"] == 2
    assert first_body["batch_total"] == 2
    assert second_body["batch_total"] == 2


def test_batch_executes_every_command_and_collects_every_protocol():
    task = {"id": 10, "store_id": 4, "payload_json": json.dumps({"store_id": 4, "commands": [
        {"intent": "card_check_in_now", "store_id": 4, "employee_afms": ["111"]},
        {"intent": "rest_day", "store_id": 4, "employee_afms": ["222"]},
    ]})}
    client = SimpleNamespace(base_url="https://example.invalid/")
    first = [{"employee": "HOXHA", "success": True, "protocol": "P-1"}]
    second = [{"employee": "ΒΗΧΟΣ", "success": True, "protocol": "P-2"}]
    with patch("app.assistant_execution_service.get_store_config", return_value={"id": 4}), \
         patch("app.assistant_execution_service.get_action_settings", return_value={"ai_agent_enabled": True}), \
         patch("app.assistant_execution_service._authenticate", return_value=("token", client)), \
         patch("app.assistant_execution_service._execute_command", side_effect=[first, second]) as execute, \
         patch("app.repo_telegram_assistant.finish_task_execution") as finish:
        result = execute_confirmed_task(task, source="assistant_telegram")
    assert result == {"success": True, "results": first + second}
    assert execute.call_count == 2
    finish.assert_called_once_with(10, success=True, result=result)
