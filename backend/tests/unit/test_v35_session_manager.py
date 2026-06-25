"""
V3.5 ResearchSessionManager unit tests.

Tests create/get/update operations on the in-memory store.
No DB or LLM calls — pure in-memory logic.
"""
import pytest

from app.research import session_manager
from app.research.models import (
    ResearchSession, ResearchPlan, ResearchReport,
    ResearchSource, ResearchStatus, SourceType,
)


def setup_function():
    session_manager._reset_for_testing()


def _make_source(url: str = "https://example.com", title: str = "Source") -> ResearchSource:
    import uuid
    return ResearchSource(
        source_id=str(uuid.uuid4()),
        title=title,
        url=url,
        source_type=SourceType.web,
        snippet="Some snippet.",
        credibility_score=0.8,
    )


def _make_plan(topic: str = "test topic") -> ResearchPlan:
    return ResearchPlan(topic=topic, queries=["test topic", "test topic overview"])


def _make_report() -> ResearchReport:
    return ResearchReport(
        executive_summary="Summary.",
        key_findings=["Finding A"],
        supporting_evidence=[],
        risks=[],
        open_questions=[],
        recommended_actions=[],
        confidence_score=0.75,
    )


# ── create_session ─────────────────────────────────────────────────────────────

class TestCreateSession:
    def test_returns_research_session(self):
        s = session_manager.create_session("conv-1", "Python")
        assert isinstance(s, ResearchSession)

    def test_topic_set(self):
        s = session_manager.create_session("conv-1", "climate change")
        assert s.topic == "climate change"

    def test_conversation_id_set(self):
        s = session_manager.create_session("conv-abc", "AI")
        assert s.conversation_id == "conv-abc"

    def test_session_id_is_unique(self):
        s1 = session_manager.create_session("c1", "topic A")
        s2 = session_manager.create_session("c2", "topic B")
        assert s1.session_id != s2.session_id

    def test_initial_status_is_active(self):
        s = session_manager.create_session("c1", "topic")
        assert s.status == ResearchStatus.active

    def test_initial_sources_empty(self):
        s = session_manager.create_session("c1", "topic")
        assert s.sources == []

    def test_initial_report_is_none(self):
        s = session_manager.create_session("c1", "topic")
        assert s.report is None

    def test_session_registered_as_active(self):
        s = session_manager.create_session("conv-new", "topic")
        active = session_manager.get_active("conv-new")
        assert active is not None
        assert active.session_id == s.session_id


# ── get_session / get_active ──────────────────────────────────────────────────

class TestGetSession:
    def test_get_by_session_id(self):
        s = session_manager.create_session("c1", "topic")
        retrieved = session_manager.get_session(s.session_id)
        assert retrieved is s

    def test_get_nonexistent_returns_none(self):
        assert session_manager.get_session("nonexistent-id") is None

    def test_get_active_returns_latest(self):
        s1 = session_manager.create_session("c1", "topic A")
        s2 = session_manager.create_session("c1", "topic B")  # replaces active
        active = session_manager.get_active("c1")
        assert active.session_id == s2.session_id

    def test_get_active_unknown_conversation_returns_none(self):
        assert session_manager.get_active("unknown-conv") is None


# ── attach_plan ────────────────────────────────────────────────────────────────

class TestAttachPlan:
    def test_plan_attached(self):
        s = session_manager.create_session("c1", "topic")
        plan = _make_plan("topic")
        session_manager.attach_plan(s, plan)
        assert s.plan is plan

    def test_updated_at_changes(self):
        s = session_manager.create_session("c1", "topic")
        original_ts = s.updated_at
        plan = _make_plan()
        session_manager.attach_plan(s, plan)
        assert s.updated_at >= original_ts


# ── add_sources ────────────────────────────────────────────────────────────────

class TestAddSources:
    def test_sources_appended(self):
        s = session_manager.create_session("c1", "topic")
        session_manager.add_sources(s, [_make_source()])
        assert len(s.sources) == 1

    def test_multiple_sources(self):
        s = session_manager.create_session("c1", "topic")
        sources = [_make_source(url=f"https://example.com/{i}") for i in range(3)]
        session_manager.add_sources(s, sources)
        assert len(s.sources) == 3

    def test_deduplication_by_url(self):
        s = session_manager.create_session("c1", "topic")
        src = _make_source(url="https://example.com/page")
        session_manager.add_sources(s, [src])
        session_manager.add_sources(s, [src])  # same URL again
        assert len(s.sources) == 1

    def test_empty_url_not_deduplicated(self):
        s = session_manager.create_session("c1", "topic")
        src1 = _make_source(url="")
        import uuid
        src2 = ResearchSource(
            source_id=str(uuid.uuid4()), title="AI", url="",
            source_type=SourceType.ai_knowledge, snippet="Content.", credibility_score=0.5,
        )
        session_manager.add_sources(s, [src1, src2])
        assert len(s.sources) == 2


# ── attach_report / mark_failed ───────────────────────────────────────────────

class TestAttachReport:
    def test_report_attached(self):
        s = session_manager.create_session("c1", "topic")
        report = _make_report()
        session_manager.attach_report(s, report)
        assert s.report is report

    def test_status_set_to_completed(self):
        s = session_manager.create_session("c1", "topic")
        session_manager.attach_report(s, _make_report())
        assert s.status == ResearchStatus.completed

    def test_synthesis_count_incremented(self):
        s = session_manager.create_session("c1", "topic")
        session_manager.attach_report(s, _make_report())
        assert s.synthesis_count == 1

    def test_synthesis_count_increments_on_repeat(self):
        s = session_manager.create_session("c1", "topic")
        session_manager.attach_report(s, _make_report())
        session_manager.attach_report(s, _make_report())
        assert s.synthesis_count == 2


class TestMarkFailed:
    def test_status_set_to_failed(self):
        s = session_manager.create_session("c1", "topic")
        session_manager.mark_failed(s)
        assert s.status == ResearchStatus.failed


# ── list / count ──────────────────────────────────────────────────────────────

class TestListAndCount:
    def setup_method(self):
        session_manager._reset_for_testing()

    def test_count_sessions(self):
        session_manager.create_session("c1", "A")
        session_manager.create_session("c2", "B")
        assert session_manager.count_sessions() == 2

    def test_list_sessions(self):
        session_manager.create_session("c1", "A")
        sessions = session_manager.list_sessions()
        assert len(sessions) >= 1
        assert all(isinstance(s, ResearchSession) for s in sessions)

    def test_reset_clears_all(self):
        session_manager.create_session("c1", "A")
        session_manager.create_session("c2", "B")
        session_manager._reset_for_testing()
        assert session_manager.count_sessions() == 0
        assert session_manager.get_active("c1") is None
