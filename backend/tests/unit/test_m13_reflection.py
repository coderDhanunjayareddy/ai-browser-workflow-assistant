"""
M1.3 — Reflection capability (bounded secondary call, gated on the Part 6 trigger).

Covers:
  - _detect_repeat_trigger (pure, deterministic trigger check)
  - _reflection_directive (pure string builder)
  - analyze() end-to-end for both providers: no-trigger single-call path (cost guarantee),
    trigger->reflect->different-action path, and reflection-failure fail-safe fallback.

No network, no real provider — the provider call functions are monkeypatched.
"""
import json

import pytest

from app.core.config import settings
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.services import ai_service
from app.services.ai_service import _detect_repeat_trigger, _reflection_directive


def _action(action_type="click", selector="#p2", description="click page 2") -> SuggestedAction:
    return SuggestedAction(
        action_id="a1", action_type=action_type, target_selector=selector,
        value=None, description=description, reasoning="trying to reach page 2",
        confidence=0.9, safety_level="safe",
    )


def _response(*actions) -> AnalyzeResponse:
    return AnalyzeResponse(session_id="s", analysis="thinking", suggested_actions=list(actions))


def _compressed(recent_actions):
    return {"verified_facts": {}, "active_goal": "g", "relevant_elements": [],
           "recent_actions": recent_actions, "important_failures": [], "task_constraints": []}


def _raw(action_type="click", selector="#p2", description="click page 2") -> str:
    return json.dumps({
        "analysis": "thinking", "clarification_question": None,
        "suggested_actions": [{
            "action_id": "a1", "action_type": action_type, "target_selector": selector,
            "value": None, "description": description, "reasoning": "r",
            "confidence": 0.9, "safety_level": "safe",
        }],
    })


# ── _detect_repeat_trigger (pure) ────────────────────────────────────────────

def test_trigger_matches_when_page_changed_unknown():
    entry = {"action_type": "click", "selector": "#p2", "page_changed": None}
    assert _detect_repeat_trigger(_response(_action()), _compressed([entry])) == entry


def test_trigger_matches_when_page_changed_false():
    entry = {"action_type": "click", "selector": "#p2", "page_changed": False}
    assert _detect_repeat_trigger(_response(_action()), _compressed([entry])) == entry


def test_trigger_does_not_match_when_page_changed_true():
    entry = {"action_type": "click", "selector": "#p2", "page_changed": True}
    assert _detect_repeat_trigger(_response(_action()), _compressed([entry])) is None


def test_trigger_none_when_selector_differs():
    entry = {"action_type": "click", "selector": "#next", "page_changed": None}
    assert _detect_repeat_trigger(_response(_action(selector="#p2")), _compressed([entry])) is None


def test_trigger_none_when_action_type_differs():
    entry = {"action_type": "fill", "selector": "#p2", "page_changed": None}
    assert _detect_repeat_trigger(_response(_action(action_type="click")), _compressed([entry])) is None


def test_trigger_none_when_no_recent_actions():
    assert _detect_repeat_trigger(_response(_action()), _compressed([])) is None
    assert _detect_repeat_trigger(_response(_action()), None) is None


def test_trigger_none_when_no_suggested_actions():
    assert _detect_repeat_trigger(_response(), _compressed([{"action_type": "click",
                                                             "selector": "#p2", "page_changed": None}])) is None


def test_trigger_ignores_non_dict_entries():
    entry = {"action_type": "click", "selector": "#p2", "page_changed": None}
    assert _detect_repeat_trigger(_response(_action()), _compressed(["not-a-dict", entry])) == entry


def test_trigger_none_when_navigate_has_no_selector():
    action = SuggestedAction(action_id="a1", action_type="navigate", target_selector="",
                             value="http://x", description="go", reasoning="r",
                             confidence=0.9, safety_level="safe")
    entry = {"action_type": "navigate", "selector": "", "page_changed": None}
    assert _detect_repeat_trigger(_response(action), _compressed([entry])) is None


# ── _reflection_directive (pure) ─────────────────────────────────────────────

def test_reflection_directive_references_specific_action():
    text = _reflection_directive({"action_type": "click", "selector": "#p2"})
    assert "click" in text and "#p2" in text
    assert "REFLECTION" in text


# ── analyze() end-to-end: OpenRouter ─────────────────────────────────────────

@pytest.fixture
def openrouter(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")


def test_openrouter_no_trigger_makes_exactly_one_call(openrouter, monkeypatch):
    calls = []
    def fake_call(messages, **kw):
        calls.append(messages)
        return _raw(selector="#next")   # no matching recent_actions entry
    monkeypatch.setattr(ai_service, "_call_openrouter_chat", fake_call)

    result = ai_service.analyze(
        session_id="s", task="paginate", page_context=_pc(), prior_steps=[],
        compressed_context=_compressed([{"action_type": "click", "selector": "#p2",
                                         "page_changed": None}]))
    assert len(calls) == 1
    assert result.suggested_actions[0].target_selector == "#next"


def test_openrouter_trigger_reflects_to_different_action(openrouter, monkeypatch):
    calls = []
    def fake_call(messages, **kw):
        calls.append(messages)
        if len(calls) == 1:
            return _raw(selector="#p2")            # repeats a no-progress action
        return _raw(selector="#next", description="click next")   # reflection response
    monkeypatch.setattr(ai_service, "_call_openrouter_chat", fake_call)

    result = ai_service.analyze(
        session_id="s", task="paginate", page_context=_pc(), prior_steps=[],
        compressed_context=_compressed([{"action_type": "click", "selector": "#p2",
                                         "page_changed": None}]))
    assert len(calls) == 2
    assert result.suggested_actions[0].target_selector == "#next"
    # the reflection instruction was actually sent to the model
    assert "REFLECTION" in calls[1][1]["content"]


def test_openrouter_reflection_failure_falls_back_to_original(openrouter, monkeypatch):
    calls = []
    def fake_call(messages, **kw):
        calls.append(messages)
        if len(calls) == 1:
            return _raw(selector="#p2")
        raise RuntimeError("provider timeout")
    monkeypatch.setattr(ai_service, "_call_openrouter_chat", fake_call)

    result = ai_service.analyze(
        session_id="s", task="paginate", page_context=_pc(), prior_steps=[],
        compressed_context=_compressed([{"action_type": "click", "selector": "#p2",
                                         "page_changed": None}]))
    assert len(calls) == 2
    # fails safe: original (repeated) action is still returned, not an error
    assert result.suggested_actions[0].target_selector == "#p2"


def test_openrouter_no_compressed_context_never_triggers(openrouter, monkeypatch):
    """Backward compatibility: callers not yet passing compressed_context (or the
    extraction-task / non-M1 code paths) must never activate reflection."""
    calls = []
    def fake_call(messages, **kw):
        calls.append(messages)
        return _raw(selector="#p2")
    monkeypatch.setattr(ai_service, "_call_openrouter_chat", fake_call)

    result = ai_service.analyze(
        session_id="s", task="paginate", page_context=_pc(), prior_steps=[],
        compressed_context=None)
    assert len(calls) == 1
    assert result.suggested_actions[0].target_selector == "#p2"


# ── analyze() end-to-end: Gemini ─────────────────────────────────────────────

class _FakeGeminiResponse:
    def __init__(self, text):
        self.text = text


class _FakeGeminiModels:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeGeminiResponse(self._responses[len(self.calls) - 1])


class _FakeGeminiClient:
    def __init__(self, responses):
        self.models = _FakeGeminiModels(responses)


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")


def test_gemini_no_trigger_makes_exactly_one_call(gemini, monkeypatch):
    fake_client = _FakeGeminiClient([_raw(selector="#next")])
    monkeypatch.setattr(ai_service.genai, "Client", lambda api_key: fake_client)

    result = ai_service.analyze(
        session_id="s", task="paginate", page_context=_pc(), prior_steps=[],
        compressed_context=_compressed([{"action_type": "click", "selector": "#p2",
                                         "page_changed": None}]))
    assert len(fake_client.models.calls) == 1
    assert result.suggested_actions[0].target_selector == "#next"


def test_gemini_trigger_reflects_to_different_action(gemini, monkeypatch):
    fake_client = _FakeGeminiClient([
        _raw(selector="#p2"),
        _raw(selector="#next", description="click next"),
    ])
    monkeypatch.setattr(ai_service.genai, "Client", lambda api_key: fake_client)

    result = ai_service.analyze(
        session_id="s", task="paginate", page_context=_pc(), prior_steps=[],
        compressed_context=_compressed([{"action_type": "click", "selector": "#p2",
                                         "page_changed": None}]))
    assert len(fake_client.models.calls) == 2
    assert result.suggested_actions[0].target_selector == "#next"


def _pc():
    from app.schemas.request import PageContext
    return PageContext(url="https://x", title="Paged List", interactive_elements=[],
                      content_blocks=[], headings=[], selected_text="", visible_text="",
                      images=[])
