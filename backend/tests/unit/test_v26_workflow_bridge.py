"""Unit tests for cognitive_core.workflow_bridge."""
import uuid

from app.cognitive_core.models import CognitiveSession, Entity, EntityType, Goal, GoalStatus
from app.cognitive_core import conversation_manager as cog_mgr
from app.cognitive_core import entity_registry
from app.cognitive_core.workflow_bridge import build_handoff_payload
from app.schemas.assist import WorkflowHandoffPayload


def setup_function():
    cog_mgr._reset_for_testing()


def _cid() -> str:
    return str(uuid.uuid4())


def _add_entity(session: CognitiveSession, name: str) -> Entity:
    e = Entity(id=str(uuid.uuid4()), type=EntityType.product, name=name, source_turn=1)
    entity_registry._upsert_entity(session, e)
    return e


# ── build_handoff_payload ─────────────────────────────────────────────────────

class TestBuildHandoffPayload:
    def test_returns_workflow_handoff_payload(self):
        session = cog_mgr.get_or_create(_cid())
        payload = build_handoff_payload("research AI", session)
        assert isinstance(payload, WorkflowHandoffPayload)

    def test_query_preserved(self):
        session = cog_mgr.get_or_create(_cid())
        payload = build_handoff_payload("research quantum computing", session)
        assert payload.query == "research quantum computing"

    def test_entities_included_in_payload(self):
        session = cog_mgr.get_or_create(_cid())
        _add_entity(session, "MacBook Air")
        _add_entity(session, "Dell XPS")
        payload = build_handoff_payload("compare them", session)
        assert len(payload.entities) == 2
        names = [e.name for e in payload.entities]
        assert "MacBook Air" in names
        assert "Dell XPS" in names

    def test_entity_fields_serialized(self):
        session = cog_mgr.get_or_create(_cid())
        _add_entity(session, "iPhone 15")
        payload = build_handoff_payload("research it", session)
        e = payload.entities[0]
        assert e.name == "iPhone 15"
        assert isinstance(e.type, str)
        assert e.confidence >= 0.0

    def test_goal_included_when_present(self):
        session = cog_mgr.get_or_create(_cid())
        from app.cognitive_core.models import Goal, GoalStatus
        import uuid
        session.active_goal = Goal(
            goal_id=str(uuid.uuid4()),
            goal_text="Compare MacBook vs Dell",
            status=GoalStatus.active,
        )
        payload = build_handoff_payload("which is better?", session)
        assert payload.goal_text == "Compare MacBook vs Dell"
        assert payload.goal_status == "active"

    def test_empty_session_has_no_goal_or_entities(self):
        session = cog_mgr.get_or_create(_cid())
        payload = build_handoff_payload("research AI", session)
        assert payload.entities == []
        assert payload.goal_text is None
        assert payload.goal_status is None

    def test_conversation_summary_included(self):
        session = cog_mgr.get_or_create(_cid())
        session.conversation_summary = "Discussing MacBook Air. Goal: Compare. Turn 1."
        payload = build_handoff_payload("compare", session)
        assert payload.conversation_summary == "Discussing MacBook Air. Goal: Compare. Turn 1."

    def test_turn_count_included(self):
        session = cog_mgr.get_or_create(_cid())
        session.turn_count = 3
        payload = build_handoff_payload("research it", session)
        assert payload.turn_count == 3

    def test_goal_handed_off_status_serialized(self):
        session = cog_mgr.get_or_create(_cid())
        import uuid
        session.active_goal = Goal(
            goal_id=str(uuid.uuid4()),
            goal_text="Research AI",
            status=GoalStatus.handed_off,
        )
        payload = build_handoff_payload("research AI", session)
        assert payload.goal_status == "handed_off"

    def test_pydantic_serialization(self):
        """Payload must be JSON-serializable (used in AssistResponse)."""
        session = cog_mgr.get_or_create(_cid())
        _add_entity(session, "MacBook Air")
        payload = build_handoff_payload("research it", session)
        d = payload.model_dump()
        assert isinstance(d, dict)
        assert "entities" in d
        assert "query" in d
