from types import SimpleNamespace

from app.services import conversation_planning
from app.services.query_planning import QueryIntent


def _settings(**overrides):
    values = {
        "conversation_planner_enabled": True,
        "conversation_planner_timeout_seconds": 4,
        "morpheus_api_key": "configured",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _history():
    return [
        {
            "turn": 3,
            "user": "What issue does PERSON_aabbccddee have?",
            "assistant": "The protected shipment was damaged.",
            "intent": "lookup",
            "citations": [
                {"ordinal": 1, "source_system": "telegram", "record_type": "message"}
            ],
        }
    ]


def test_planner_parses_strict_json_and_uses_short_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr(conversation_planning, "get_settings", lambda: _settings())

    def fake_chat(messages, *, temperature, timeout_seconds):
        captured["messages"] = messages
        captured["temperature"] = temperature
        captured["timeout"] = timeout_seconds
        return (
            '```json\n{"intent":"lookup","referenced_turn":3,'
            '"response_style":"compact","needs_clarification":false}\n```'
        )

    monkeypatch.setattr(conversation_planning, "morpheus_chat", fake_chat)
    result = conversation_planning.plan_conversation(
        history=_history(),
        protected_question="Suggest a response",
        current_intent=QueryIntent.LOOKUP,
        available_sources=["email", "telegram"],
    )

    assert result is not None
    assert result.referenced_turn == 3
    assert result.query_intent is QueryIntent.LOOKUP
    assert captured["temperature"] == 0.0
    assert captured["timeout"] == 4
    assert "PERSON_aabbccddee" in captured["messages"][1]["content"]


def test_planner_failure_and_unknown_turn_fall_back_without_raising(monkeypatch):
    monkeypatch.setattr(conversation_planning, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        conversation_planning,
        "morpheus_chat",
        lambda *_args, **_kwargs: (
            '{"intent":"lookup","referenced_turn":99,'
            '"response_style":"compact","needs_clarification":false}'
        ),
    )

    assert (
        conversation_planning.plan_conversation(
            history=_history(),
            protected_question="Suggest a response",
            current_intent=QueryIntent.LOOKUP,
            available_sources=["telegram"],
        )
        is None
    )


def test_exact_query_intents_never_call_morpheus(monkeypatch):
    monkeypatch.setattr(conversation_planning, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        conversation_planning,
        "morpheus_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must bypass model")),
    )

    assert (
        conversation_planning.plan_conversation(
            history=_history(),
            protected_question="Show all email",
            current_intent=QueryIntent.LIST_RECORDS,
            available_sources=["email"],
        )
        is None
    )


def test_planner_privacy_preflight_refuses_unprotected_history(monkeypatch):
    monkeypatch.setattr(conversation_planning, "get_settings", lambda: _settings())
    monkeypatch.setattr(
        conversation_planning,
        "morpheus_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not expose PII")),
    )
    unsafe_history = _history()
    unsafe_history[0]["assistant"] = "Contact the customer at raw.person@example.com"

    assert (
        conversation_planning.plan_conversation(
            history=unsafe_history,
            protected_question="Suggest a response",
            current_intent=QueryIntent.LOOKUP,
            available_sources=["telegram"],
        )
        is None
    )
