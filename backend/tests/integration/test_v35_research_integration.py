"""
V3.5 Research Engine — Integration Tests.

Tests full research pipeline through ambient_assistant.run() with research intent.
All AI provider calls (DDG, AI knowledge, synthesis, LLM) are mocked.
"""
import json
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.schemas.assist import AssistRequest, ReadView
from app.assist.ambient_assistant import run
from app.conversation import manager as conversation_manager
from app.cognitive_core import conversation_manager as cog_mgr
from app.cognitive_core import analytics as cog_analytics
from app.research import session_manager, analytics as research_analytics


def setup_function():
    conversation_manager._reset_store_for_testing()
    cog_mgr._reset_for_testing()
    cog_analytics._reset_for_testing()
    session_manager._reset_for_testing()
    research_analytics._reset_for_testing()


def _cid() -> str:
    return f"rv35-{uuid.uuid4().hex[:8]}"


def _rv(text: str = "Python is a popular programming language.") -> ReadView:
    return ReadView(
        url="https://python.org",
        title="Python Home",
        visible_text=text,
        headings=["Python"],
        metadata={},
    )


def _req(message: str, cid: str) -> AssistRequest:
    return AssistRequest(
        conversation_id=cid,
        message=message,
        read_view=_rv(),
        selection_scope="page",
    )


def _mock_synthesis_json() -> str:
    return json.dumps({
        "executive_summary": "Python is a versatile language.",
        "key_findings": ["Finding 1", "Finding 2"],
        "supporting_evidence": [
            {"finding": "Finding 1", "source_title": "Wikipedia",
             "source_url": "https://en.wikipedia.org/wiki/Python", "is_conclusion": False}
        ],
        "risks": ["Risk 1"],
        "open_questions": ["What next?"],
        "recommended_actions": ["Learn Python"],
        "confidence_score": 0.75,
    })


def _ddg_response(abstract: str = "Python is a language.", heading: str = "Python") -> dict:
    return {
        "AbstractText": abstract,
        "AbstractURL": "https://en.wikipedia.org/wiki/Python",
        "AbstractSource": "Wikipedia",
        "Heading": heading,
        "RelatedTopics": [],
    }


# ── Full pipeline integration ─────────────────────────────────────────────────

class TestResearchPipelineIntegration:
    def _mock_http_and_synthesis(self):
        """Returns context managers for patching DDG HTTP call and synthesis LLM."""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _ddg_response()
        mock_response.raise_for_status = MagicMock()
        return mock_response

    def test_research_intent_returns_research_report_type(self):
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                resp = run(_req("research Python programming", cid))
        assert resp.type == "research_report"

    def test_research_routed_to_research_engine(self):
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                resp = run(_req("research Python programming", cid))
        assert resp.routed_to == "research"
        assert resp.intent == "research"

    def test_research_report_field_populated(self):
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                resp = run(_req("research Python programming", cid))
        assert resp.research_report is not None
        assert resp.research_report.executive_summary == "Python is a versatile language."

    def test_research_report_sources_include_page_context(self):
        """Page context is always included as a source."""
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                resp = run(_req("research Python programming", cid))
        assert resp.research_report is not None
        source_types = [s.source_type for s in resp.research_report.sources]
        assert "page_context" in source_types

    def test_research_creates_session_in_manager(self):
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                run(_req("research Python programming", cid))
        active = session_manager.get_active(cid)
        assert active is not None
        assert active.topic == "Python programming"

    def test_research_increments_analytics(self):
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        before = research_analytics.get_analytics()["sessions_started"]
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                run(_req("research Python programming", cid))
        after = research_analytics.get_analytics()["sessions_started"]
        assert after == before + 1

    def test_research_appends_turns_to_conversation(self):
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                run(_req("research Python programming", cid))
        turns = conversation_manager.get_thread(cid)
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].intent == "research"
        assert turns[1].role == "assistant"

    def test_research_error_returns_not_implemented(self):
        """If research engine raises, return graceful fallback."""
        cid = _cid()
        with patch("app.research.engine.run_research", side_effect=Exception("provider failed")):
            resp = run(_req("research quantum entanglement", cid))
        assert resp.type == "not_implemented"
        assert resp.intent == "research"

    def test_pure_research_has_no_handoff_payload(self):
        """Research without action keywords → handoff_payload is None."""
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                resp = run(_req("research Python programming", cid))
        assert resp.handoff_payload is None

    def test_research_with_action_keyword_sets_handoff_payload(self):
        """Research with action keywords (buy, book) → handoff_payload set."""
        cid = _cid()
        mock_resp = self._mock_http_and_synthesis()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                resp = run(_req("research and buy Python books", cid))
        assert resp.handoff_payload is not None
        assert resp.handoff.available is True


# ── Multi-turn research ───────────────────────────────────────────────────────

class TestMultiTurnResearch:
    def _run_research(self, cid: str, message: str) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _ddg_response()
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.return_value = mock_resp
            with patch("app.services.ai_service.generate_text", return_value=_mock_synthesis_json()):
                return run(_req(message, cid))

    def test_second_research_creates_new_session(self):
        cid = _cid()
        self._run_research(cid, "research Python")
        first = session_manager.get_active(cid)
        self._run_research(cid, "research Django")
        second = session_manager.get_active(cid)
        assert first.session_id != second.session_id
        assert second.topic == "Django"

    def test_cognitive_session_updated_per_turn(self):
        cid = _cid()
        self._run_research(cid, "research Python")
        session = cog_mgr.get_session(cid)
        assert session is not None
        assert session.turn_count == 1

    def test_research_count_accumulates(self):
        cid = _cid()
        before = research_analytics.get_analytics()["sessions_started"]
        self._run_research(cid, "research Python")
        self._run_research(cid, "research Django")
        after = research_analytics.get_analytics()["sessions_started"]
        assert after == before + 2


# ── Regression: existing paths unaffected ────────────────────────────────────

class TestResearchRegression:
    def test_summarize_path_unchanged(self):
        cid = _cid()
        summary_json = json.dumps({
            "tldr": "Summary here.",
            "key_points": [],
            "entities": [],
            "available_actions": [],
        })
        with patch("app.services.ai_service.generate_text", return_value=summary_json):
            with patch("app.services.followup_service.generate", return_value=[]):
                resp = run(AssistRequest(
                    conversation_id=cid,
                    message="summarize this page",
                    read_view=_rv(),
                    selection_scope="page",
                ))
        assert resp.type == "summary"
        assert resp.routed_to == "light"
        assert resp.research_report is None

    def test_ask_path_unchanged(self):
        cid = _cid()
        with patch("app.services.ai_service.generate_text", return_value="Answer here."):
            resp = run(AssistRequest(
                conversation_id=cid,
                message="what is Python?",
                read_view=_rv(),
                selection_scope="page",
            ))
        assert resp.type == "answer"
        assert resp.research_report is None

    def test_compare_path_unchanged(self):
        cid = _cid()
        resp = run(AssistRequest(
            conversation_id=cid,
            message="compare Python vs JavaScript",
            read_view=_rv(),
            selection_scope="page",
        ))
        assert resp.type == "not_implemented"
        assert resp.routed_to == "fallback"
        assert resp.research_report is None
