"""
V2.5 Slice 4 unit tests — Handoff Protocol.

Updated for V3.5: Research now routes through the Research Engine (not fallback).
- Pure research queries (no action keywords) return type="research_report", handoff.available=False.
- Research queries WITH action keywords return handoff.available=True.
- Compare / unknown still use the fallback path with handoff.available=True.
All LLM calls and the research engine are mocked.
"""
import uuid
from unittest.mock import patch, MagicMock

from app.schemas.assist import ReadView, AssistRequest


def _make_request(message: str, **rv_kwargs) -> AssistRequest:
    defaults = dict(
        url="https://example.com",
        title="Example Page",
        visible_text="Some example page content about Python.",
    )
    defaults.update(rv_kwargs)
    return AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message=message,
        read_view=ReadView(**defaults),
        context_fingerprint="test-fp",
        selection_scope="page",
    )


def _reset():
    from app.conversation import manager as conversation_manager
    conversation_manager._reset_store_for_testing()


def _mock_summary() -> str:
    import json
    return json.dumps({
        "tldr": "A short summary.",
        "key_points": [],
        "entities": [],
        "available_actions": [],
    })


def _stub_research_session(topic: str = "test topic", with_handoff: bool = False):
    """Return a stub (rsession, handoff) for mocking run_research."""
    from app.research.models import (
        ResearchSession, ResearchReport, ResearchStatus,
    )
    from app.schemas.assist import WorkflowHandoffPayload
    rsession = ResearchSession(
        session_id="stub-sid",
        conversation_id="stub-cid",
        topic=topic,
        status=ResearchStatus.completed,
    )
    rsession.report = ResearchReport(
        executive_summary=f"Research on {topic} complete.",
        key_findings=["Finding A"],
        supporting_evidence=[],
        risks=[],
        open_questions=[],
        recommended_actions=[],
        confidence_score=0.7,
    )
    handoff = None
    if with_handoff:
        handoff = WorkflowHandoffPayload(
            query=f"book {topic}",
            goal_text=None,
            goal_status=None,
            entities=[],
            conversation_summary="",
            turn_count=1,
        )
    return rsession, handoff


# ── Handoff available for fallback intents ───────────────────────────────────

class TestHandoffForFallbackIntents:
    """
    V3.5: Research queries with action keywords get handoff.available=True.
    Pure research queries (no action keywords) get handoff.available=False.
    Compare / unknown still return handoff.available=True via fallback path.
    """

    def test_research_with_action_keyword_returns_handoff_available(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research and book quantum computing course")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("quantum computing", with_handoff=True)):
            resp = run(req)
        assert resp.handoff.available is True

    def test_pure_research_handoff_not_available(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research quantum computing")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("quantum computing")):
            resp = run(req)
        assert resp.handoff.available is False

    def test_compare_returns_handoff_available(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("compare iPhone vs Samsung")
        resp = run(req)
        assert resp.handoff.available is True

    def test_unknown_intent_returns_handoff_available(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("book me a flight to Tokyo")
        resp = run(req)
        assert resp.handoff.available is True

    def test_research_action_keyword_handoff_target_is_workflow(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research and buy artificial intelligence book")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("ai book", with_handoff=True)):
            resp = run(req)
        assert resp.handoff.target == "workflow"

    def test_research_routes_to_research_engine(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("look up the history of this topic")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("history")) as mock_engine:
            resp = run(req)
        mock_engine.assert_called_once()
        assert resp.routed_to == "research"

    def test_compare_handoff_target_string(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("comparison of React and Vue")
        resp = run(req)
        assert isinstance(resp.handoff.target, str)


# ── Handoff NOT available for handled intents ────────────────────────────────

class TestHandoffNotAvailableForLightPath:
    def test_summarize_handoff_not_available(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("summarize this page")
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                resp = run(req)
        assert resp.handoff.available is False

    def test_ask_handoff_not_available(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("what is this page about?")
        with patch("app.services.ai_service.generate_text", return_value="This page is about Python."):
            resp = run(req)
        assert resp.handoff.available is False

    def test_summarize_handoff_target_is_none(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("summarize this page")
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                resp = run(req)
        assert resp.handoff.target is None

    def test_ask_handoff_target_is_none(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("what are the key points?")
        with patch("app.services.ai_service.generate_text", return_value="Here are the key points."):
            resp = run(req)
        assert resp.handoff.target is None


# ── Research Engine response integrity ────────────────────────────────────────

class TestHandoffResponseIntegrity:
    def test_research_response_type_is_research_report(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research the history of Python")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("history of Python")):
            resp = run(req)
        assert resp.type == "research_report"

    def test_research_routed_to_research(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research artificial intelligence")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("artificial intelligence")):
            resp = run(req)
        assert resp.routed_to == "research"

    def test_research_response_content_is_string(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research artificial intelligence")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("artificial intelligence")):
            resp = run(req)
        assert isinstance(resp.content, str)
        assert len(resp.content) > 0

    def test_research_response_has_research_report_field(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research machine learning frameworks")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("machine learning")):
            resp = run(req)
        assert resp.research_report is not None
        assert resp.research_report.topic == "machine learning"

    def test_compare_response_has_summarize_followup_suggestion(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("compare iPhone vs Android")
        resp = run(req)
        assert "Summarize this page" in resp.suggested_followups

    def test_research_has_suggested_followups(self):
        _reset()
        from app.assist.ambient_assistant import run
        req = _make_request("research machine learning frameworks")
        with patch("app.research.engine.run_research",
                   return_value=_stub_research_session("machine learning")):
            resp = run(req)
        assert len(resp.suggested_followups) > 0

    def test_fallback_intents_still_have_handoff(self):
        """Compare and unknown fallback paths still return handoff.available=True."""
        _reset()
        from app.assist.ambient_assistant import run
        fallback_messages = [
            "compare Android and iPhone",
            "book me a restaurant",
        ]
        for msg in fallback_messages:
            req = _make_request(msg)
            resp = run(req)
            assert resp.handoff.available is True, f"Expected handoff for: {msg}"
            assert resp.handoff.target == "workflow", f"Expected target=workflow for: {msg}"
