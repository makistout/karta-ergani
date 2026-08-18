from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import requests
from flask import Flask

from app.routes_telegram import telegram_bp
from app.repo_telegram_assistant import create_task
from app.telegram_assistant_service import parse_command, validate_and_describe


def _app():
    app = Flask(__name__)
    app.register_blueprint(telegram_bp)
    return app


def test_checkout_validation_skips_already_closed_cards():
    parsed = {
        "intent": "card_check_out_now",
        "store_id": 4,
        "employee_afms": ["111222333", "444555666"],
        "date": "2026-08-18",
    }
    employees = [
        {"store_id": 4, "afm": "111222333", "name": "OPEN ONE"},
        {"store_id": 4, "afm": "444555666", "name": "CLOSED TWO"},
    ]

    def fake_guard(*, employee_afm, **kwargs):
        if employee_afm == "444555666":
            return "Η κάρτα έχει ήδη κλείσει (δήλωση εξόδου)"
        return None

    with patch("app.work_card_guards.new_card_punch_blocked_reason", side_effect=fake_guard):
        status, validation, proposed = validate_and_describe(
            parsed,
            contexts=[{
                "store_id": 4,
                "store_name": "ERATO",
                "employer_afm": "123456789",
                "branch_aa": "0",
            }],
            employees=employees,
        )
    assert status == "draft"
    assert validation["valid"] is True
    assert parsed["employee_afms"] == ["111222333"]
    assert "Παραλείφθηκαν" in proposed
    assert "CLOSED TWO" in proposed


def test_employee_catalog_only_includes_active_store_employees():
    from app.telegram_assistant_service import _employee_catalog

    contexts = [{"store_id": 4, "employer_afm": "123456789", "branch_aa": "0"}]
    rows = [
        {"afm": "111222333", "eponymo": "ΕΝΕΡΓΟΣ", "onoma": "ΕΝΑ", "active": 1},
        {"afm": "444555666", "eponymo": "ΑΝΕΝΕΡΓΟΣ", "onoma": "ΔΥΟ", "active": 0},
    ]
    with patch(
        "app.telegram_assistant_service.list_active_employees_for_store",
        return_value=rows,
    ) as listed:
        catalog = _employee_catalog(contexts)
    listed.assert_called_once_with("123456789", "0", limit=1000)
    assert catalog == [{"store_id": 4, "afm": "111222333", "name": "ΕΝΕΡΓΟΣ ΕΝΑ"}]


def test_unknown_chat_is_silently_ignored():
    payload = {"update_id": 10, "message": {"message_id": 20, "chat": {"id": 999}, "text": "άνοιξε κάρτα τώρα"}}
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=[]), \
         patch("app.routes_telegram._reply_chat") as reply:
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    reply.assert_not_called()


def test_store_without_ai_agent_gets_activation_message_and_is_not_parsed():
    payload = {"update_id": 15, "message": {"message_id": 25, "chat": {"id": 123}, "text": "άνοιξε κάρτα τώρα"}}
    contexts = [{
        "recipient_id": 7, "store_id": 4, "store_name": "ERATO",
        "ai_agent_enabled": 0,
    }]
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.telegram_assistant_service.parse_command") as parse, \
         patch("app.routes_telegram._reply_chat") as reply, \
         patch("app.routes_telegram.Config.AI_AGENT_CONTACT_PHONE", "2100000000"):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "assistant": "store_disabled"}
    parse.assert_not_called()
    assert reply.call_args.args[1] == (
        "Ο ΑΙ agent δεν είναι ενεργοποιημένος. "
        "Καλέστε στο 2100000000 για να ενημερωθείτε για το κόστος ενεργοποίησης του."
    )


def test_mixed_store_chat_only_exposes_ai_enabled_store_to_parser():
    payload = {"update_id": 16, "message": {"message_id": 26, "chat": {"id": 123}, "text": "άνοιξε κάρτα τώρα"}}
    contexts = [
        {"recipient_id": 7, "store_id": 4, "store_name": "OFF", "ai_agent_enabled": 0},
        {"recipient_id": 8, "store_id": 5, "store_name": "ON", "ai_agent_enabled": 1},
    ]
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(36, True)), \
         patch("app.repo_telegram_assistant.reply_context", return_value=None), \
         patch("app.repo_telegram_assistant.create_task", return_value=46), \
         patch("app.repo_telegram_assistant.mark_inbound"), \
         patch("app.telegram_assistant_service.parse_command", side_effect=RuntimeError("stop")) as parse, \
         patch("app.routes_telegram._reply_chat"), \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        _app().test_client().post("/api/telegram/webhook", json=payload)
    assert parse.call_args.kwargs["contexts"] == [contexts[1]]


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
    llm_metadata = {
        "model": "gemini-flash-latest",
        "duration_ms": 321,
        "usage_metadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 20,
            "totalTokenCount": 120,
        },
    }
    with patch("app.repo_telegram_assistant.authorized_contexts", return_value=contexts), \
         patch("app.repo_telegram_assistant.conversation_task") as conversation_task, \
         patch("app.repo_telegram_assistant.create_inbound_message", return_value=(31, True)), \
         patch("app.repo_telegram_assistant.reply_context", return_value=None), \
         patch("app.repo_telegram_assistant.create_task", return_value=41) as create_task, \
         patch("app.repo_telegram_assistant.mark_inbound") as mark, \
         patch("app.telegram_assistant_service.parse_command", return_value=(parsed, employees, llm_metadata)), \
         patch("app.routes_telegram._reply_chat") as reply, \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.status_code == 200
    assert create_task.call_args.kwargs["status"] == "awaiting_pin"
    assert create_task.call_args.kwargs["validation"]["execution_enabled"] is False
    assert create_task.call_args.kwargs["llm_metadata"] == llm_metadata
    assert reply.call_args.args[1] == "Εντολή #41:\nΔΟΚΙΜΗ ΧΡΗΣΤΗΣ · 15/08/2026 · Άνοιγμα κάρτας τώρα"
    assert reply.call_args.kwargs["reply_markup"] == {
        "inline_keyboard": [[{"text": "Επιβεβαίωση με PIN", "callback_data": "assistant_confirm:41"}]]
    }
    assert reply.call_args.kwargs["context"]["notification_type"] == "assistant_pin"
    conversation_task.assert_not_called()
    mark.assert_called_with(31, "parsed")


def test_correct_pin_is_redacted_and_executes_without_gemini():
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
         patch("app.assistant_execution_service.execute_confirmed_task", return_value={
             "success": True, "results": [{"employee": "HOXHA", "success": True, "protocol": "P-1"}],
         }) as execute, \
         patch("app.routes_telegram._reply_chat") as reply, \
         patch("app.routes_telegram.Config.TELEGRAM_ASSISTANT_ENABLED", True):
        response = _app().test_client().post("/api/telegram/webhook", json=payload)
    assert response.get_json()["assistant"] == "completed"
    assert create_inbound.call_args.kwargs["text"] == "[REDACTED_PIN]"
    assert create_inbound.call_args.kwargs["raw_payload"]["message"]["text"] == "[REDACTED_PIN]"
    verify.assert_called_once_with(41, chat_id="123", pin="1234")
    execute.assert_called_once_with(conversation, source="assistant_telegram")
    parse.assert_not_called()
    assert "Πρωτόκολλο: P-1" in reply.call_args.args[1]


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
    assert proposed == "ΔΟΚΙΜΗ ΧΡΗΣΤΗΣ · 16/08/2026 · Αλλαγή ωραρίου σε 09:00–17:00"


def test_schedule_card_uses_real_start_time_and_greek_date():
    parsed = {
        "intent": "card_check_in_schedule", "store_id": 4,
        "employee_afms": ["111222333"], "date": "2026-08-17",
    }
    with patch("app.repo_schedule.list_schedule_for_store", return_value=[
        {"employee_afm": "111222333", "hour_from": "09:00", "hour_to": "17:00"},
    ]) as schedule:
        status, validation, proposed = validate_and_describe(
            parsed,
            contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "123", "branch_aa": "0"}],
            employees=[{"store_id": 4, "afm": "111222333", "name": "HOXHA DASHURI"}],
        )
    assert status == "draft"
    assert validation["valid"] is True
    assert parsed["resolved_schedule_times"] == {"111222333": "09:00"}
    assert proposed == "HOXHA DASHURI · 17/08/2026 · Άνοιγμα κάρτας 09:00"
    schedule.assert_called_once_with("123", "0", "17/08/2026")


def test_multiple_different_commands_are_validated_as_one_batch():
    parsed = {"commands": [
        {"intent": "card_check_in_now", "store_id": 4, "employee_afms": ["111"],
         "employee_references": ["HOXHA"], "date": "2026-08-17"},
        {"intent": "rest_day", "store_id": 4, "employee_afms": ["222"],
         "employee_references": ["ΒΗΧΟΣ"], "date": "2026-08-18"},
    ]}
    with patch("app.work_card_guards.new_card_punch_blocked_reason", return_value=None):
        status, validation, proposed = validate_and_describe(
            parsed,
            contexts=[{"store_id": 4, "store_name": "ERATO"}],
            employees=[
                {"store_id": 4, "afm": "111", "name": "HOXHA DASHURI"},
                {"store_id": 4, "afm": "222", "name": "ΒΗΧΟΣ ΙΩΑΝΝΗΣ"},
            ],
        )
    assert status == "draft"
    assert validation["valid"] is True
    assert parsed["store_id"] == 4
    assert proposed.splitlines() == [
        "HOXHA DASHURI · 17/08/2026 · Άνοιγμα κάρτας τώρα",
        "ΒΗΧΟΣ ΙΩΑΝΝΗΣ · 18/08/2026 · Δήλωση ρεπό",
    ]


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


def test_today_info_question_is_answered_without_action():
    parsed = {
        "intent": "today_info",
        "store_id": 4,
        "employee_afms": [],
        "date": None,
        "clarification_question": (
            "Οι εργαζόμενοι που τελειώνουν στις 20:40 είναι οι: "
            "Μουρατίδου Αλεξάνδρα, Πουραβέλη Ανδρομάχη και Καραγιάννη Νικολίτσα."
        ),
    }
    status, validation, proposed = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        employees=[{"store_id": 4, "afm": "111222333", "name": "ΜΟΥΡΑΤΙΔΟΥ ΑΛΕΞΑΝΔΡΑ"}],
    )
    assert status == "answered"
    assert validation["valid"] is True
    assert validation["execution_enabled"] is False
    assert "Μουρατίδου Αλεξάνδρα" in proposed
    assert "20:40" in proposed


def test_today_info_without_answer_needs_clarification():
    parsed = {
        "intent": "today_info",
        "store_id": 4,
        "employee_afms": [],
    }
    status, validation, _ = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO"}],
        employees=[],
    )
    assert status == "needs_clarification"
    assert validation["valid"] is False
    assert "Δεν δόθηκε απάντηση από την εικόνα εργασίας σήμερα" in validation["errors"]


def test_today_info_conversation_returns_plain_answer():
    from app.assistant_conversation_service import process_assistant_command

    parsed = {
        "intent": "today_info",
        "store_id": 4,
        "employee_afms": [],
        "clarification_question": "Η Μασούρα τελειώνει στις 20:40.",
    }
    with patch(
        "app.telegram_assistant_service.parse_command",
        return_value=(parsed, [], {"model": "test"}),
    ), patch("app.repo_telegram_assistant.create_task", return_value=29) as create_task, \
       patch("app.repo_telegram_assistant.mark_inbound"):
        result = process_assistant_command(
            text="ti ora teleionei h masoura",
            contexts=[{"store_id": 4, "store_name": "VILLA SHARM", "recipient_id": 7}],
            inbound_id=1,
            confirmation_mode="ui",
        )
    assert result["status"] == "answered"
    assert result["task_status"] == "answered"
    assert result["answer"] == "Η Μασούρα τελειώνει στις 20:40."
    assert create_task.call_args.kwargs["status"] == "answered"


def test_future_card_punch_date_is_rejected():
    parsed = {
        "intent": "card_check_in_schedule",
        "store_id": 4,
        "employee_afms": ["111222333"],
        "date": "2099-01-01",
    }
    status, validation, _ = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "123456789", "branch_aa": "0"}],
        employees=[{"store_id": 4, "afm": "111222333", "name": "ΔΟΚΙΜΗ ΧΡΗΣΤΗΣ"}],
    )
    assert status == "needs_clarification"
    assert validation["valid"] is False
    assert "Η ώρα κίνησης δεν μπορεί να είναι μελλοντική" in validation["errors"]


def test_future_card_punch_time_today_is_rejected():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    future_time = (datetime.now(ZoneInfo("Europe/Athens")) + timedelta(hours=2)).strftime("%H:%M")
    today = datetime.now(ZoneInfo("Europe/Athens")).date().isoformat()
    parsed = {
        "intent": "card_check_in_retro",
        "store_id": 4,
        "employee_afms": ["111222333"],
        "date": today,
        "time": future_time,
    }
    status, validation, _ = validate_and_describe(
        parsed,
        contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "123456789", "branch_aa": "0"}],
        employees=[{"store_id": 4, "afm": "111222333", "name": "ΔΟΚΙΜΗ ΧΡΗΣΤΗΣ"}],
    )
    assert status == "needs_clarification"
    assert validation["valid"] is False
    assert any("Η ώρα κίνησης δεν μπορεί να είναι μελλοντική" in item for item in validation["errors"])


def test_task_persists_gemini_usage_metadata():
    cur = MagicMock()
    cur.fetchone.side_effect = [None, (77,)]

    @contextmanager
    def fake_cursor():
        yield cur

    metadata = {
        "model": "gemini-2.5-flash",
        "duration_ms": 456,
        "usage_metadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 20,
            "totalTokenCount": 125,
            "cachedContentTokenCount": 5,
            "thoughtsTokenCount": 5,
            "toolUsePromptTokenCount": 0,
            "futureMetric": 9,
        },
    }
    with patch("app.repo_telegram_assistant.cursor", fake_cursor):
        task_id = create_task(
            inbound_id=31, recipient_id=7, store_id=4,
            parsed={
                "intent": "rest_day", "employee_afms": ["111222333"],
                "date": "2026-08-15", "confidence": 0.95,
            },
            status="awaiting_pin",
            validation={"valid": True, "execution_enabled": False},
            proposed_action="Δήλωση ρεπό",
            llm_metadata=metadata,
        )
    assert task_id == 77
    insert_sql, insert_params = cur.execute.call_args_list[1].args
    assert insert_sql.count("?") == len(insert_params)
    assert insert_params[-9:-1] == (
        "gemini-2.5-flash", 100, 20, 125, 5, 5, 0, 456,
    )
    assert '"futureMetric": 9' in insert_params[-1]


def test_gemini_transient_503_is_retried_then_succeeds():
    unavailable = MagicMock(ok=False, status_code=503, text="high demand")
    success = MagicMock(ok=True, status_code=200)
    success.json.return_value = {
        "modelVersion": "gemini-3.5-flash-lite",
        "candidates": [{"content": {"parts": [{"text": '{"intent":"card_check_in_now","store_id":4,"employee_afms":["111222333"],"employee_references":["HOXHA"],"date":"2026-08-17","time":null,"hour_from":null,"hour_to":null,"leave_type":null,"confidence":0.99,"clarification_question":null}'}]}}],
        "usageMetadata": {"totalTokenCount": 25},
    }
    contexts = [{"store_id": 4, "store_name": "ERATO", "employer_afm": "123", "branch_aa": "0"}]
    employees = [{"store_id": 4, "afm": "111222333", "name": "HOXHA ARBEN"}]
    with patch("app.telegram_assistant_service.Config.GEMINI_API_KEY", "test"), \
         patch("app.telegram_assistant_service.Config.GEMINI_MODEL", "gemini-3.5-flash-lite"), \
         patch("app.telegram_assistant_service.Config.GEMINI_FALLBACK_MODEL", "gemini-3.5-flash"), \
         patch("app.telegram_assistant_service._employee_catalog", return_value=employees), \
         patch("app.telegram_assistant_service.build_today_home_context", return_value={"date": "2026-08-17", "stores": []}), \
         patch("app.telegram_assistant_service.requests.post", side_effect=[unavailable, success]) as post, \
         patch("app.telegram_assistant_service.time.sleep") as sleep:
        parsed, returned_employees, metadata = parse_command(text="άνοιξε την κάρτα του HOXHA", contexts=contexts)
    assert post.call_count == 2
    assert "gemini-3.5-flash-lite" in post.call_args_list[0].args[0]
    assert "gemini-3.5-flash" in post.call_args_list[1].args[0]
    sleep.assert_not_called()
    assert parsed["intent"] == "card_check_in_now"
    assert returned_employees == employees
    assert metadata["usage_metadata"]["totalTokenCount"] == 25


def test_gemini_timeout_fails_over_to_secondary_model():
    success = MagicMock(ok=True, status_code=200)
    success.json.return_value = {
        "modelVersion": "gemini-3.5-flash",
        "candidates": [{"content": {"parts": [{"text": '{"intent":"card_check_in_schedule","store_id":4,"employee_afms":["111222333"],"employee_references":["HOXHA"],"date":"2026-08-17","time":null,"hour_from":null,"hour_to":null,"leave_type":null,"confidence":0.99,"clarification_question":null}'}]}}],
        "usageMetadata": {"totalTokenCount": 25},
    }
    contexts = [{"store_id": 4, "store_name": "ERATO", "employer_afm": "123", "branch_aa": "0"}]
    employees = [{"store_id": 4, "afm": "111222333", "name": "HOXHA ARBEN"}]
    with patch("app.telegram_assistant_service.Config.GEMINI_API_KEY", "test"), \
         patch("app.telegram_assistant_service.Config.GEMINI_MODEL", "gemini-3.5-flash-lite"), \
         patch("app.telegram_assistant_service.Config.GEMINI_FALLBACK_MODEL", "gemini-3.5-flash"), \
         patch("app.telegram_assistant_service._employee_catalog", return_value=employees), \
         patch("app.telegram_assistant_service.build_today_home_context", return_value={"date": "2026-08-17", "stores": []}), \
         patch("app.telegram_assistant_service.requests.post", side_effect=[requests.Timeout("slow"), success]) as post:
        parsed, _, metadata = parse_command(text="βάσει ωραρίου", contexts=contexts)
    assert post.call_count == 2
    assert parsed["intent"] == "card_check_in_schedule"
    assert metadata["model"] == "gemini-3.5-flash"
