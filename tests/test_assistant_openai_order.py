"""Tests για ASSISTANT_LLM_ORDER με OpenAI failover + latency guards."""

from app.telegram_assistant_service import parse_command


def test_llm_order_openai_after_gemini_failure(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_ORDER",
        "gemini,openai",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_WALL_SEC",
        8.0,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.GEMINI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.OPENAI_API_KEY",
        "sk-test",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_RULE_FALLBACK_ENABLED",
        False,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda _contexts: [{"store_id": 9, "afm": "1", "name": "A"}],
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.build_today_home_context",
        lambda _contexts: {"stores": []},
    )

    def boom_gemini(*_a, **_k):
        calls.append("gemini")
        raise RuntimeError("503")

    def fake_openai(*, prompt_obj, timeout_sec=20.0):
        calls.append("openai")
        return {
            "intent": "card_check_in_now",
            "employee_afms": ["1"],
            "employee_references": [],
            "confidence": 0.9,
            "clarification_question": None,
            "store_id": 9,
        }, {"model": "gpt-5.5", "provider": "openai", "duration_ms": 12}

    monkeypatch.setattr("app.telegram_assistant_service._call_gemini", boom_gemini)
    monkeypatch.setattr("app.openai_assistant_client.openai_enabled", lambda: True)
    monkeypatch.setattr("app.openai_assistant_client.generate_json", fake_openai)

    parsed, _emps, meta = parse_command(
        text="άνοιξε κάρτα του Α",
        contexts=[{"store_id": 9, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
    )
    assert calls == ["gemini", "openai"]
    assert meta["llm_used"] == "openai"
    assert parsed["intent"] == "card_check_in_now"


def test_rules_last_after_all_llm_fail(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_ORDER",
        "gemini,openai",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_RULE_FALLBACK_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.GEMINI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.OPENAI_API_KEY",
        "sk-test",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda _contexts: [{"store_id": 9, "afm": "1", "name": "A"}],
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.build_today_home_context",
        lambda _contexts: {
            "stores": [{
                "store_id": 9,
                "name": "ERATO",
                "employees": [{
                    "afm": "1",
                    "name": "A",
                    "status": "at_work",
                    "card_in": "10:00",
                    "schedule_to": "18:00",
                }],
                "summary": {"at_work": 1, "completed": 0, "rest": 0},
            }],
        },
    )

    def boom_gemini(*_a, **_k):
        calls.append("gemini")
        raise RuntimeError("503")

    def boom_openai(*, prompt_obj, timeout_sec=20.0):
        calls.append("openai")
        raise RuntimeError("timeout")

    monkeypatch.setattr("app.telegram_assistant_service._call_gemini", boom_gemini)
    monkeypatch.setattr("app.openai_assistant_client.openai_enabled", lambda: True)
    monkeypatch.setattr("app.openai_assistant_client.generate_json", boom_openai)

    parsed, _emps, meta = parse_command(
        text="ποιοι εργάζονται ακόμα",
        contexts=[{"store_id": 9, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
    )
    assert calls == ["gemini", "openai"]
    assert meta["llm_used"] == "rules"
    assert parsed["intent"] == "today_info"
    assert "A" in (parsed.get("clarification_question") or "")


def test_openai_always_after_gemini_failure(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_ORDER",
        "gemini,openai",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_WALL_SEC",
        3.0,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.OPENAI_TIMEOUT_SEC",
        6.0,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.GEMINI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.OPENAI_API_KEY",
        "sk-test",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_RULE_FALLBACK_ENABLED",
        False,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda _contexts: [{"store_id": 9, "afm": "1", "name": "A"}],
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.build_today_home_context",
        lambda _contexts: {"stores": []},
    )

    def slow_fail_gemini(*_a, **_k):
        import time

        calls.append("gemini")
        time.sleep(2.6)
        raise RuntimeError("timeout")

    def fake_openai(*, prompt_obj, timeout_sec=20.0):
        calls.append("openai")
        return {
            "intent": "card_check_in_now",
            "employee_afms": ["1"],
            "employee_references": [],
            "confidence": 0.9,
            "store_id": 9,
        }, {"model": "gpt", "provider": "openai", "duration_ms": 1}

    monkeypatch.setattr("app.telegram_assistant_service._call_gemini", slow_fail_gemini)
    monkeypatch.setattr("app.openai_assistant_client.openai_enabled", lambda: True)
    monkeypatch.setattr("app.openai_assistant_client.generate_json", fake_openai)

    parsed, _emps, meta = parse_command(
        text="άνοιξε κάρτα του Α",
        contexts=[{"store_id": 9, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
    )
    assert calls == ["gemini", "openai"]
    assert meta["llm_used"] == "openai"
    assert parsed["intent"] == "card_check_in_now"


def test_extract_openai_output_text():
    from app.openai_assistant_client import _extract_output_text

    data = {
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": '{"intent":"today_info"}'}],
        }],
    }
    assert _extract_output_text(data) == '{"intent":"today_info"}'
