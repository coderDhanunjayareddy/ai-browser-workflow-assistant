"""Unit tests for cognitive_core.conversation_manager."""
import uuid
from unittest.mock import patch

from app.cognitive_core import conversation_manager as cog_mgr
from app.cognitive_core.models import CognitiveSession, GoalStatus


def setup_function():
    cog_mgr._reset_for_testing()


def _cid() -> str:
    return str(uuid.uuid4())


# ── Session lifecycle ─────────────────────────────────────────────────────────

class TestSessionLifecycle:
    def test_get_or_create_returns_new_session(self):
        session = cog_mgr.get_or_create(_cid())
        assert isinstance(session, CognitiveSession)
        assert session.turn_count == 0

    def test_get_or_create_returns_same_session(self):
        cid = _cid()
        s1 = cog_mgr.get_or_create(cid)
        s2 = cog_mgr.get_or_create(cid)
        assert s1 is s2

    def test_different_ids_get_different_sessions(self):
        s1 = cog_mgr.get_or_create(_cid())
        s2 = cog_mgr.get_or_create(_cid())
        assert s1 is not s2

    def test_session_limit_evicts_oldest(self):
        from app.cognitive_core.conversation_manager import MAX_SESSIONS
        ids = [_cid() for _ in range(MAX_SESSIONS + 2)]
        for cid in ids:
            cog_mgr.get_or_create(cid)
        # Oldest ids should have been evicted
        assert cog_mgr.get_session(ids[0]) is None


# ── process_turn ──────────────────────────────────────────────────────────────

class TestProcessTurn:
    def test_turn_count_increments(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        cog_mgr.process_turn(session, intent="ask", message="hello", response_type="answer")
        assert session.turn_count == 1

    def test_active_intent_updated(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        cog_mgr.process_turn(session, intent="research", message="research AI", response_type="not_implemented")
        assert session.active_intent == "research"

    def test_summary_entities_extracted(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        cog_mgr.process_turn(
            session,
            intent="summarize",
            message="summarize",
            summary_entities=[{"label": "Product", "value": "MacBook Air"}],
            response_type="summary",
        )
        assert len(session.active_entities) == 1
        entity = list(session.active_entities.values())[0]
        assert entity.name == "MacBook Air"

    def test_message_entities_extracted_compare(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        cog_mgr.process_turn(
            session,
            intent="compare",
            message="compare MacBook Air and Dell XPS",
            response_type="not_implemented",
        )
        names = {e.name for e in session.active_entities.values()}
        assert "MacBook Air" in names
        assert "Dell XPS" in names

    def test_goal_created_on_first_turn(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        cog_mgr.process_turn(session, intent="ask", message="What is this?", response_type="answer")
        assert session.active_goal is not None

    def test_conversation_summary_updated(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        cog_mgr.process_turn(
            session,
            intent="compare",
            message="compare A and B",
            response_type="not_implemented",
        )
        assert session.conversation_summary != ""
        assert "Turn" in session.conversation_summary

    def test_handoff_sets_goal_to_handed_off(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        cog_mgr.process_turn(
            session,
            intent="research",
            message="research AI",
            response_type="not_implemented",
            handoff_triggered=True,
        )
        assert session.active_goal.status == GoalStatus.handed_off

    def test_returns_new_entities_list(self):
        cid = _cid()
        session = cog_mgr.get_or_create(cid)
        new_entities = cog_mgr.process_turn(
            session,
            intent="compare",
            message="compare iPhone and Samsung",
            response_type="not_implemented",
        )
        assert isinstance(new_entities, list)


# ── Analytics ─────────────────────────────────────────────────────────────────

class TestAnalytics:
    def test_get_analytics_structure(self):
        analytics = cog_mgr.get_analytics()
        assert "active_sessions" in analytics
        assert "total_entities" in analytics
        assert "goal_statuses" in analytics

    def test_active_sessions_count(self):
        for _ in range(3):
            cog_mgr.get_or_create(_cid())
        analytics = cog_mgr.get_analytics()
        assert analytics["active_sessions"] >= 3
