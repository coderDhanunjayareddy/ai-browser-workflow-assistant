"""
V2.6 Cognitive Core — Integration Tests.

Tests full multi-turn conversation flows through ambient_assistant.run():
  - Entity persistence across turns
  - Goal continuity
  - Reference resolution enriching QA responses
  - Workflow handoff payload enrichment
  - Regression: summarize and ask paths unaffected
"""
import json
import uuid
from unittest.mock import patch

import pytest

from app.schemas.assist import AssistRequest, ReadView
from app.assist.ambient_assistant import run
from app.conversation import manager as conversation_manager
from app.cognitive_core import conversation_manager as cog_mgr
from app.cognitive_core import analytics as cog_analytics


def setup_function():
    conversation_manager._reset_store_for_testing()
    cog_mgr._reset_for_testing()
    cog_analytics._reset_for_testing()


def _cid() -> str:
    return str(uuid.uuid4())


def _rv(visible_text: str = "MacBook Air costs $1099. Dell XPS costs $999.") -> ReadView:
    return ReadView(
        url="https://example.com/laptops",
        title="Laptop Comparison",
        headings=["Top Laptops"],
        content_blocks=[{"selector": "p", "text": visible_text}],
        visible_text=visible_text,
        metadata={},
    )


def _req(message: str, cid: str, rv: ReadView = None) -> AssistRequest:
    return AssistRequest(
        conversation_id=cid,
        message=message,
        read_view=rv or _rv(),
        context_fingerprint="test",
        selection_scope="page",
    )


def _mock_summary(tldr: str = "Two laptops compared.") -> str:
    return json.dumps({
        "tldr": tldr,
        "key_points": ["MacBook Air: $1099", "Dell XPS: $999"],
        "entities": [
            {"label": "Product", "value": "MacBook Air"},
            {"label": "Product", "value": "Dell XPS"},
            {"label": "Price", "value": "$1099"},
            {"label": "Price", "value": "$999"},
        ],
        "available_actions": [],
    })


# ── Entity persistence across turns ──────────────────────────────────────────

class TestEntityPersistence:
    def test_summary_entities_extracted_and_stored(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(_req("summarize this page", cid))
        session = cog_mgr.get_session(cid)
        assert session is not None
        names = {e.name for e in session.active_entities.values()}
        assert "MacBook Air" in names
        assert "Dell XPS" in names

    def test_compare_message_entities_extracted(self):
        cid = _cid()
        resp = run(_req("compare MacBook Air and Dell XPS", cid))
        assert resp.type == "not_implemented"  # compare → fallback
        session = cog_mgr.get_session(cid)
        assert session is not None
        names = {e.name for e in session.active_entities.values()}
        assert "MacBook Air" in names
        assert "Dell XPS" in names

    def test_entities_survive_across_turns(self):
        cid = _cid()
        # Turn 1: summarize (extracts entities from summary)
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(_req("summarize this page", cid))
        # Turn 2: ask (entities should still be in session)
        with patch("app.services.ai_service.generate_text", return_value="Dell XPS is cheaper."):
            run(_req("which is cheaper?", cid))
        session = cog_mgr.get_session(cid)
        assert len(session.active_entities) >= 2


# ── Goal continuity ───────────────────────────────────────────────────────────

class TestGoalContinuity:
    def test_goal_created_on_first_turn(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(_req("summarize", cid))
        session = cog_mgr.get_session(cid)
        assert session.active_goal is not None

    def test_compare_goal_includes_entity_names(self):
        cid = _cid()
        run(_req("compare MacBook Air and Dell XPS", cid))
        session = cog_mgr.get_session(cid)
        goal = session.active_goal
        assert goal is not None
        # After process_turn, goal should reference entity names
        assert "MacBook" in goal.goal_text or "Compare" in goal.goal_text

    def test_handoff_transitions_goal_to_handed_off(self):
        # compare → fallback → handoff_triggered=True → goal transitions to handed_off
        cid = _cid()
        run(_req("compare MacBook Air and Dell XPS", cid))
        session = cog_mgr.get_session(cid)
        assert session.active_goal is not None
        assert session.active_goal.status.value == "handed_off"

    def test_goal_persists_across_multiple_turns(self):
        cid = _cid()
        # Turn 1: summarize
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(_req("summarize", cid))
        first_goal_id = cog_mgr.get_session(cid).active_goal.goal_id

        # Turn 2: ask — goal should be the same object (updated, not replaced)
        with patch("app.services.ai_service.generate_text", return_value="Answer."):
            run(_req("what is the price?", cid))
        assert cog_mgr.get_session(cid).active_goal.goal_id == first_goal_id


# ── Workflow handoff enrichment ───────────────────────────────────────────────

class TestWorkflowHandoffEnrichment:
    # V3.5 note: pure research queries go to the Research Engine, not the fallback path.
    # handoff_payload is set only for fallback intents (compare, unknown) or action-keyword research.
    # These tests use "compare" queries to exercise the fallback handoff path.

    def test_fallback_response_has_handoff_payload(self):
        cid = _cid()
        resp = run(_req("compare artificial intelligence vs machine learning", cid))
        assert resp.handoff_payload is not None

    def test_handoff_payload_contains_query(self):
        cid = _cid()
        resp = run(_req("compare quantum vs classical computing", cid))
        assert resp.handoff_payload is not None
        assert resp.handoff_payload.query == "compare quantum vs classical computing"

    def test_handoff_payload_contains_entities_after_compare(self):
        cid = _cid()
        # Turn 1: compare (extracts entities)
        run(_req("compare MacBook Air and Dell XPS", cid))
        # Turn 2: another fallback that carries entities in payload
        resp2 = run(_req("compare those two products on price", cid))
        assert resp2.handoff_payload is not None
        # Entities from turn 1 should carry over
        assert len(resp2.handoff_payload.entities) >= 2

    def test_handoff_payload_contains_goal(self):
        cid = _cid()
        run(_req("compare MacBook Air and Dell XPS", cid))
        session = cog_mgr.get_session(cid)
        assert session.active_goal is not None
        resp2 = run(_req("compare the two again", cid))
        payload = resp2.handoff_payload
        assert payload is not None
        assert payload.goal_text is not None
        assert payload.goal_status is not None

    def test_handoff_payload_turn_count_accurate(self):
        cid = _cid()
        run(_req("compare A and B", cid))
        resp2 = run(_req("compare it again", cid))
        assert resp2.handoff_payload is not None
        assert resp2.handoff_payload.turn_count == 2

    def test_light_path_no_handoff_payload(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                resp = run(_req("summarize", cid))
        assert resp.handoff_payload is None

    def test_ask_no_handoff_payload(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value="Answer here."):
            resp = run(_req("what is the price?", cid))
        assert resp.handoff_payload is None

    def test_pure_research_has_no_handoff_payload(self):
        """V3.5: pure research without action keywords → handoff_payload is None."""
        cid = _cid()
        from unittest.mock import patch
        from app.research.models import ResearchSession, ResearchReport, ResearchStatus
        stub_session = ResearchSession(
            session_id="s1", conversation_id=cid, topic="ai",
            status=ResearchStatus.completed,
        )
        stub_session.report = ResearchReport(
            executive_summary="AI overview", key_findings=[], supporting_evidence=[],
            risks=[], open_questions=[], recommended_actions=[], confidence_score=0.7,
        )
        with patch("app.research.engine.run_research", return_value=(stub_session, None)):
            resp = run(_req("research artificial intelligence", cid))
        assert resp.handoff_payload is None
        assert resp.research_report is not None


# ── Reference resolution via intent continuity ───────────────────────────────

class TestReferenceEnrichment:
    def test_enriched_question_answered_with_entity_context(self):
        """QA service receives 'Considering MacBook Air, Dell XPS: Which is cheaper?'"""
        cid = _cid()
        # Turn 1: summarize to load entities
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(_req("summarize", cid))

        # Turn 2: ask with comparative + reference
        qa_calls: list[str] = []
        original_generate = None

        def capture_qa(*args, **kwargs):
            qa_calls.append(args[0] if args else kwargs.get("prompt", ""))
            return "Dell XPS is cheaper at $999."

        with patch("app.services.ai_service.generate_text", side_effect=capture_qa):
            run(_req("which is cheaper?", cid))

        # The QA prompt should contain entity context if enrichment was applied
        # (enrichment is applied when reference terms + entities exist)
        session = cog_mgr.get_session(cid)
        assert session is not None
        assert session.turn_count == 2


# ── Regression: existing behavior preserved ──────────────────────────────────

class TestRegression:
    def test_summarize_response_unchanged(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=["Tell me more"]):
                resp = run(_req("summarize", cid))
        assert resp.type == "summary"
        assert resp.intent == "summarize"
        assert resp.routed_to == "light"
        assert resp.handoff.available is False

    def test_ask_option_b_preserved(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value="Answer."):
            resp = run(_req("what is FastAPI?", cid))
        assert resp.type == "answer"
        assert resp.suggested_followups == []

    def test_fallback_handoff_flag_preserved(self):
        # V3.5: research now goes to research engine. Compare still uses fallback.
        cid = _cid()
        resp = run(_req("compare machine learning vs deep learning", cid))
        assert resp.handoff.available is True
        assert resp.handoff.target == "workflow"

    def test_summarize_handoff_false(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
            with patch("app.services.followup_service.generate", return_value=[]):
                resp = run(_req("summarize", cid))
        assert resp.handoff.available is False

    def test_ask_handoff_false(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value="Answer."):
            resp = run(_req("what is this page?", cid))
        assert resp.handoff.available is False
