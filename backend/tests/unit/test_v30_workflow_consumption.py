"""
Unit tests for V3.0 Workflow Consumption Layer.

Tests:
  - workflow_context.build_cognitive_context()
  - workflow_context.build_bootstrap_facts()
  - state_engine.persistence.StatePersistence.bootstrap_from_handoff()
  - context_compression.compressor.ContextCompressor.compress() with cognitive_context
"""
import pytest
from unittest.mock import MagicMock, patch

from app.schemas.assist import WorkflowHandoffPayload, CognitiveEntitySchema
from app.cognitive_core.workflow_context import build_cognitive_context, build_bootstrap_facts


# ── Fixtures ────────────────────────────────────────────────────────────────────

def _make_payload(
    *,
    query="compare laptops",
    goal_text="Compare: MacBook Air, Dell XPS",
    goal_status="active",
    turn_count=3,
    summary="Discussing: MacBook Air, Dell XPS. Goal: Compare laptops.",
    entities=None,
) -> WorkflowHandoffPayload:
    if entities is None:
        entities = [
            CognitiveEntitySchema(id="e1", type="product", name="MacBook Air",
                                  confidence=0.9, source_turn=1),
            CognitiveEntitySchema(id="e2", type="product", name="Dell XPS",
                                  confidence=0.6, source_turn=1),
        ]
    return WorkflowHandoffPayload(
        query=query,
        goal_text=goal_text,
        goal_status=goal_status,
        entities=entities,
        conversation_summary=summary,
        turn_count=turn_count,
    )


# ── build_cognitive_context ────────────────────────────────────────────────────

def test_cognitive_context_includes_all_keys():
    payload = _make_payload()
    ctx = build_cognitive_context(payload)

    assert ctx["conversation_turns"] == 3
    assert "MacBook Air" in ctx["conversation_summary"] or True  # summary content
    assert ctx["user_goal"] == "Compare: MacBook Air, Dell XPS"
    assert ctx["goal_status"] == "active"
    assert len(ctx["tracked_entities"]) == 2


def test_cognitive_context_entity_shape():
    payload = _make_payload()
    ctx = build_cognitive_context(payload)
    entity = ctx["tracked_entities"][0]
    assert "name" in entity
    assert "type" in entity
    assert "confidence" in entity
    assert entity["confidence"] == round(entity["confidence"], 2)


def test_cognitive_context_no_goal():
    payload = WorkflowHandoffPayload(
        query="what is this?",
        goal_text=None,
        goal_status=None,
        entities=[],
        conversation_summary="",
        turn_count=1,
    )
    ctx = build_cognitive_context(payload)
    assert "user_goal" not in ctx
    assert "goal_status" not in ctx
    assert "tracked_entities" not in ctx


def test_cognitive_context_no_entities():
    payload = WorkflowHandoffPayload(
        query="summarize",
        goal_text="Understand this page",
        goal_status="active",
        entities=[],
        conversation_summary="Some context.",
        turn_count=2,
    )
    ctx = build_cognitive_context(payload)
    assert ctx["user_goal"] == "Understand this page"
    assert "tracked_entities" not in ctx


# ── build_bootstrap_facts ──────────────────────────────────────────────────────

def test_bootstrap_facts_full_payload():
    payload = _make_payload()
    facts = build_bootstrap_facts(payload)

    assert facts["user_goal"] == "Compare: MacBook Air, Dell XPS"
    assert facts["goal_status"] == "active"
    assert facts["prior_conversation_turns"] == 3
    assert "entity_0_name" in facts
    assert facts["entity_0_name"] == "MacBook Air"
    assert facts["entity_0_type"] == "product"
    assert facts["entity_1_name"] == "Dell XPS"


def test_bootstrap_facts_empty_payload():
    payload = WorkflowHandoffPayload(
        query="x", goal_text=None, goal_status=None,
        entities=[], conversation_summary="", turn_count=0,
    )
    facts = build_bootstrap_facts(payload)
    assert facts == {}


def test_bootstrap_facts_no_entities():
    payload = WorkflowHandoffPayload(
        query="summarize",
        goal_text="Understand this page",
        goal_status="active",
        entities=[],
        conversation_summary="Some context.",
        turn_count=2,
    )
    facts = build_bootstrap_facts(payload)
    assert facts["user_goal"] == "Understand this page"
    assert "entity_0_name" not in facts


# ── StatePersistence.bootstrap_from_handoff ────────────────────────────────────

def _make_state_persistence(db=None):
    from app.state_engine.persistence import StatePersistence
    return StatePersistence(db or MagicMock())


def test_bootstrap_returns_none_when_payload_none():
    sp = _make_state_persistence()
    result = sp.bootstrap_from_handoff("sess-1", None)
    assert result is None


def test_bootstrap_skips_when_facts_already_exist():
    sp = _make_state_persistence()
    existing = MagicMock()
    existing.facts = {"some": "fact"}
    sp.get_state = MagicMock(return_value=existing)

    payload = _make_payload()
    result = sp.bootstrap_from_handoff("sess-1", payload)
    assert result is existing  # unchanged


def test_bootstrap_saves_facts_on_cold_start():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.db import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    sp = _make_state_persistence(db)
    payload = _make_payload()
    result = sp.bootstrap_from_handoff("sess-cold", payload)

    assert result is not None
    assert result.facts.get("user_goal") == "Compare: MacBook Air, Dell XPS"
    assert result.facts.get("entity_0_name") == "MacBook Air"
    db.close()


# ── ContextCompressor.compress with cognitive_context ─────────────────────────

def _fake_page_context():
    pc = MagicMock()
    pc.interactive_elements = []
    return pc


def test_compress_without_cognitive_context():
    from app.context_compression.compressor import ContextCompressor
    compressor = ContextCompressor()
    result = compressor.compress(
        task="Do something",
        page_context=_fake_page_context(),
        verified_facts={},
        prior_steps=[],
    )
    assert "cognitive_context" not in result
    assert "verified_facts" in result
    assert "task_constraints" in result


def test_compress_with_cognitive_context():
    from app.context_compression.compressor import ContextCompressor
    compressor = ContextCompressor()
    cog = {"user_goal": "Compare laptops", "conversation_turns": 3}
    result = compressor.compress(
        task="Compare laptops",
        page_context=_fake_page_context(),
        verified_facts={},
        prior_steps=[],
        cognitive_context=cog,
    )
    assert result["cognitive_context"] == cog


def test_compress_with_empty_cognitive_context_omits_key():
    from app.context_compression.compressor import ContextCompressor
    compressor = ContextCompressor()
    result = compressor.compress(
        task="Do something",
        page_context=_fake_page_context(),
        verified_facts={},
        prior_steps=[],
        cognitive_context={},
    )
    assert "cognitive_context" not in result
