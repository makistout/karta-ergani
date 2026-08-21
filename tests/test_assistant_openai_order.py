"""Tests για ASSISTANT_LLM_ORDER με OpenAI failover."""

from app.telegram_assistant_service import parse_command


def test_llm_order_openai_after_gemini_failure(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_ORDER",
        "gemini,openai",
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
            "intent": "today_info",
            "employee_afms": [],
            "employee_references": [],
            "confidence": 0.9,
            "clarification_question": "ok",
            "store_id": 9,
        }, {"model": "gpt-5.5", "provider": "openai", "duration_ms": 12}

    monkeypatch.setattr("app.telegram_assistant_service._call_gemini", boom_gemini)
    monkeypatch.setattr("app.openai_assistant_client.openai_enabled", lambda: True)
    monkeypatch.setattr("app.openai_assistant_client.generate_json", fake_openai)

    parsed, _emps, meta = parse_command(
        text="ποιοι εργάζονται",
        contexts=[{"store_id": 9, "store_name": "ERATO", "employer_afm": "1", "branch_aa": "0"}],
    )
    assert calls == ["gemini", "openai"]
    assert meta["llm_used"] == "openai"
    assert parsed["intent"] == "today_info"


def test_extract_openai_output_text():
    from app.openai_assistant_client import _extract_output_text

    data = {
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": '{"intent":"today_info"}'}],
        }],
    }
    assert _extract_output_text(data) == '{"intent":"today_info"}'
