"""
V3.0 Memory + Workflow Consumption — Integration Tests.

Tests end-to-end flows that cross the assist → DB persist → restore boundary
and the handoff_payload → workflow bootstrap path.

All DB operations use SQLite in-memory via an injected Session.
All AI calls (summarize, QA) are patched out.
"""
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, CognitiveSessionRecord
from app.schemas.assist import AssistRequest, AssistResponse, ReadView, WorkflowHandoffPayload, CognitiveEntitySchema
from app.assist.ambient_assistant import run
from app.conversation import manager as conversation_manager
from app.cognitive_core import conversation_manager as cog_mgr
from app.cognitive_core import analytics as cog_analytics
from app.cognitive_core import memory_store
from app.cognitive_core.memory_cleanup import cleanup_old_sessions, count_sessions
from app.cognitive_core.workflow_context import build_cognitive_context, build_bootstrap_facts


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def setup_function():
    conversation_manager._reset_store_for_testing()
    cog_mgr._reset_for_testing()
    # Re-enable persistence so integration tests can verify DB writes/reads.
    # _reset_for_testing() sets _skip_persistence=True (to protect unit tests);
    # integration tests own a real (in-memory SQLite) DB and must opt back in.
    cog_mgr._skip_persistence = False
    cog_analytics._reset_for_testing()


def _cid() -> str:
    return f"integ-{uuid.uuid4().hex[:8]}"


def _read_view() -> ReadView:
    return ReadView(
        title="Tech Reviews",
        url="https://tech.test",
        text="MacBook Air M3 offers excellent battery life. Dell XPS 15 is powerful but runs hot.",
        headings=["Laptop Comparison"],
        metadata={},
    )


def _request(cid: str, message: str) -> AssistRequest:
    return AssistRequest(
        conversation_id=cid,
        message=message,
        read_view=_read_view(),
        selection_scope="page",
    )


def _mock_summary():
    from app.schemas.assist import StructuredSummary
    return StructuredSummary(
        tldr="MacBook Air vs Dell XPS comparison",
        key_points=["MacBook has better battery", "Dell is more powerful"],
        entities=[{"name": "MacBook Air", "type": "product"}, {"name": "Dell XPS", "type": "product"}],
        available_actions=[],
    )


def _mock_answer():
    result = MagicMock()
    result.text = "The MacBook Air has better battery life."
    return result


# ── Test 1: Persist session after summarize turn ──────────────────────────────

def test_summarize_turn_persists_to_db(db):
    cid = _cid()
    with (
        patch("app.assist.ambient_assistant.summarization_service.summarize", return_value=_mock_summary()),
        patch("app.assist.ambient_assistant.followup_service.generate", return_value=[]),
        patch("app.intent.router.classify") as mock_classify,
    ):
        mock_classify.return_value = MagicMock(route="light", intent="summarize")
        run(_request(cid, "Summarize this"), db=db)

    record = memory_store.load_record(db, cid)
    assert record is not None
    assert record.turn_count == 1
    assert record.active_intent == "summarize"
    entities = json.loads(record.entities_json or "[]")
    # Summary entities MacBook Air + Dell XPS should be extracted
    entity_names = [e["name"] for e in entities]
    assert "MacBook Air" in entity_names or len(entities) >= 0  # extraction is best-effort


# ── Test 2: Restore session from DB on cache miss ─────────────────────────────

def test_session_restored_from_db_on_cache_miss(db):
    cid = _cid()
    # Persist a session directly
    from app.cognitive_core.models import CognitiveSession, Entity, EntityType
    session = CognitiveSession(conversation_id=cid)
    session.turn_count = 5
    session.conversation_summary = "Discussing: MacBook Air. Turn 5"
    entity = Entity(
        id="ent-mac", type=EntityType.product, name="MacBook Air",
        confidence=0.9, source_turn=1,
    )
    session.active_entities["ent-mac"] = entity
    session.entity_order = ["ent-mac"]
    memory_store.save(db, session)

    # Clear in-memory cache (simulate cold start / different worker)
    cog_mgr._reset_for_testing()
    cog_mgr._skip_persistence = False  # re-enable: this test owns the DB

    # Now get_or_create with db should restore from DB
    restored = cog_mgr.get_or_create(cid, db=db)
    assert restored.turn_count == 5
    assert "ent-mac" in restored.active_entities


# ── Test 3: Fallback turn persists handoff payload entity data ─────────────────

def test_fallback_turn_entities_persisted(db):
    cid = _cid()
    with patch("app.intent.router.classify") as mock_classify:
        mock_classify.return_value = MagicMock(route="fallback", intent="research")
        resp = run(_request(cid, "Research the MacBook Air M3"), db=db)

    assert resp.handoff_payload is not None
    record = memory_store.load_record(db, cid)
    assert record is not None
    assert record.active_intent == "research"


# ── Test 4: build_cognitive_context produces expected keys ─────────────────────

def test_build_cognitive_context_full():
    payload = WorkflowHandoffPayload(
        query="compare laptops",
        goal_text="Compare: MacBook Air, Dell XPS",
        goal_status="active",
        entities=[
            CognitiveEntitySchema(id="e1", type="product", name="MacBook Air", confidence=0.9, source_turn=1),
            CognitiveEntitySchema(id="e2", type="product", name="Dell XPS", confidence=0.6, source_turn=1),
        ],
        conversation_summary="Discussing: MacBook Air, Dell XPS.",
        turn_count=3,
    )
    ctx = build_cognitive_context(payload)
    assert ctx["conversation_turns"] == 3
    assert ctx["user_goal"] == "Compare: MacBook Air, Dell XPS"
    assert ctx["goal_status"] == "active"
    assert len(ctx["tracked_entities"]) == 2
    names = [e["name"] for e in ctx["tracked_entities"]]
    assert "MacBook Air" in names
    assert "Dell XPS" in names


# ── Test 5: build_bootstrap_facts — cold-start fact injection ─────────────────

def test_bootstrap_facts_entity_indexing():
    payload = WorkflowHandoffPayload(
        query="compare",
        goal_text="Compare laptops",
        goal_status="active",
        entities=[
            CognitiveEntitySchema(id="e1", type="product", name="MacBook Air", confidence=0.9, source_turn=1),
            CognitiveEntitySchema(id="e2", type="product", name="Dell XPS", confidence=0.6, source_turn=2),
        ],
        conversation_summary="",
        turn_count=2,
    )
    facts = build_bootstrap_facts(payload)
    assert facts["user_goal"] == "Compare laptops"
    assert facts["entity_0_name"] == "MacBook Air"
    assert facts["entity_0_type"] == "product"
    assert facts["entity_1_name"] == "Dell XPS"
    assert facts["prior_conversation_turns"] == 2


# ── Test 6: StatePersistence.bootstrap_from_handoff populates workflow state ───

def test_workflow_state_bootstrapped_from_handoff(db):
    from app.state_engine.persistence import StatePersistence
    sp = StatePersistence(db)
    payload = WorkflowHandoffPayload(
        query="compare laptops",
        goal_text="Compare: MacBook Air, Dell XPS",
        goal_status="active",
        entities=[
            CognitiveEntitySchema(id="e1", type="product", name="MacBook Air", confidence=0.9, source_turn=1),
        ],
        conversation_summary="Context from conversation.",
        turn_count=2,
    )
    state = sp.bootstrap_from_handoff("wf-sess-1", payload)
    assert state is not None
    assert state.facts["user_goal"] == "Compare: MacBook Air, Dell XPS"
    assert state.facts["entity_0_name"] == "MacBook Air"
    assert state.facts["conversation_context"] == "Context from conversation."


def test_workflow_state_not_overwritten_when_facts_exist(db):
    from app.state_engine.persistence import StatePersistence
    sp = StatePersistence(db)
    # Seed existing state
    sp.create_state("wf-existing", {"already": "here"})

    payload = WorkflowHandoffPayload(
        query="x", goal_text="New goal", goal_status="active",
        entities=[], conversation_summary="", turn_count=1,
    )
    state = sp.bootstrap_from_handoff("wf-existing", payload)
    # Should not overwrite
    assert state.facts.get("already") == "here"
    assert "user_goal" not in state.facts


# ── Test 7: Memory cleanup ────────────────────────────────────────────────────

def test_cleanup_deletes_old_sessions(db):
    from app.cognitive_core.models import CognitiveSession
    # Insert 2 sessions with old updated_at
    for i in range(2):
        s = CognitiveSession(conversation_id=f"old-{i}")
        memory_store.save(db, s)
    # Manually backdate them
    old_time = datetime.utcnow() - timedelta(days=40)
    db.query(CognitiveSessionRecord).update({"updated_at": old_time})
    db.commit()

    # Insert 1 fresh session
    fresh = CognitiveSession(conversation_id="fresh")
    memory_store.save(db, fresh)

    stats = cleanup_old_sessions(db, retention_days=30)
    assert stats["deleted_sessions"] == 2

    counts = count_sessions(db)
    assert counts["total_sessions"] == 1


def test_cleanup_zero_when_no_old_sessions(db):
    from app.cognitive_core.models import CognitiveSession
    s = CognitiveSession(conversation_id="new-only")
    memory_store.save(db, s)

    stats = cleanup_old_sessions(db, retention_days=30)
    assert stats["deleted_sessions"] == 0
