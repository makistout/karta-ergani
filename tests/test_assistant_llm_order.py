"""Tests για ASSISTANT_LLM_ORDER."""

from app.telegram_assistant_service import parse_command


def test_llm_order_local_first(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_ORDER",
        "local,gemini",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.GEMINI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.LOCAL_LLM_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_RULE_FALLBACK_ENABLED",
        False,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda contexts: [],
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.build_today_home_context",
        lambda contexts: {"date": "2026-08-20", "stores": []},
    )

    def fake_gemini(prompt, *, deadline):
        calls.append("gemini")
        raise RuntimeError("should not be primary")

    def fake_local(*, prompt_obj, schema, timeout_sec):
        calls.append("local")
        return {
            "intent": "today_info",
            "employee_afms": [],
            "employee_references": [],
            "confidence": 1.0,
            "clarification_question": "ok",
        }, {"model": "local:test", "provider": "ollama"}

    monkeypatch.setattr("app.telegram_assistant_service._call_gemini", fake_gemini)
    monkeypatch.setattr("app.local_llm_client.local_llm_enabled", lambda: True)
    monkeypatch.setattr("app.local_llm_client.generate_json", fake_local)

    parsed, _emps, meta = parse_command(
        text="τεστ",
        contexts=[{"store_id": 9, "store_name": "ERATO", "employer_afm": "091065232", "branch_aa": "0"}],
    )
    assert calls == ["local"]
    assert meta.get("llm_used") == "local"
    assert parsed["intent"] == "today_info"


def test_llm_order_gemini_only_skips_local(monkeypatch):
    calls: list[str] = []

    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_LLM_ORDER",
        "gemini",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.GEMINI_API_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.Config.ASSISTANT_RULE_FALLBACK_ENABLED",
        False,
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service._employee_catalog",
        lambda contexts: [],
    )
    monkeypatch.setattr(
        "app.telegram_assistant_service.build_today_home_context",
        lambda contexts: {"date": "2026-08-20", "stores": []},
    )

    def fake_gemini(prompt, *, deadline):
        calls.append("gemini")
        return {
            "intent": "unknown",
            "employee_afms": [],
            "employee_references": [],
            "confidence": 0.5,
            "clarification_question": "?",
        }, {"model": "gemini-test", "provider": "gemini"}

    def boom(*_a, **_k):
        calls.append("local")
        raise AssertionError("local must not run")

    monkeypatch.setattr("app.telegram_assistant_service._call_gemini", fake_gemini)
    monkeypatch.setattr("app.local_llm_client.local_llm_enabled", lambda: True)
    monkeypatch.setattr("app.local_llm_client.generate_json", boom)

    parsed, _emps, meta = parse_command(
        text="τεστ",
        contexts=[{"store_id": 9, "store_name": "ERATO", "employer_afm": "091065232", "branch_aa": "0"}],
    )
    assert calls == ["gemini"]
    assert meta.get("llm_used") == "gemini"
    assert parsed["intent"] == "unknown"
