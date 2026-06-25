"""
Unit tests for V3.0 MemoryStore: serialization round-trips and DB persistence.

Uses SQLite in-memory so no real PostgreSQL is needed.
"""
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, CognitiveSessionRecord
from app.cognitive_core.models import CognitiveSession, Entity, EntityType, Goal, GoalStatus
from app.cognitive_core import memory_store


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def _make_session(conversation_id: str = "conv-1") -> CognitiveSession:
    s = CognitiveSession(conversation_id=conversation_id)
    s.turn_count = 3
    s.conversation_summary = "Discussing: MacBook Air. Goal: Compare laptops. Turn 3"
    s.active_intent = "compare"
    entity = Entity(
        id="ent-mac",
        type=EntityType.product,
        name="MacBook Air",
        aliases=["MacBook"],
        metadata={"brand": "Apple"},
        confidence=0.9,
        source_turn=1,
    )
    s.active_entities["ent-mac"] = entity
    s.entity_order = ["ent-mac"]
    s.active_goal = Goal(
        goal_id="goal-1",
        goal_text="Compare: MacBook Air",
        status=GoalStatus.active,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
    )
    return s


# ── save / load round-trip ─────────────────────────────────────────────────────

def test_save_and_load_round_trip(db):
    original = _make_session("round-trip")
    memory_store.save(db, original)

    restored = memory_store.load(db, "round-trip")

    assert restored is not None
    assert restored.conversation_id == "round-trip"
    assert restored.turn_count == 3
    assert restored.active_intent == "compare"
    assert restored.conversation_summary == original.conversation_summary
    assert "ent-mac" in restored.active_entities
    mac = restored.active_entities["ent-mac"]
    assert mac.name == "MacBook Air"
    assert mac.type == EntityType.product
    assert mac.confidence == 0.9
    assert mac.aliases == ["MacBook"]
    assert mac.metadata == {"brand": "Apple"}
    assert restored.entity_order == ["ent-mac"]
    assert restored.active_goal is not None
    assert restored.active_goal.goal_text == "Compare: MacBook Air"
    assert restored.active_goal.status == GoalStatus.active


def test_load_nonexistent_returns_none(db):
    result = memory_store.load(db, "does-not-exist")
    assert result is None


def test_load_record_returns_raw(db):
    s = _make_session("raw-rec")
    memory_store.save(db, s)
    record = memory_store.load_record(db, "raw-rec")
    assert record is not None
    assert isinstance(record, CognitiveSessionRecord)
    assert record.turn_count == 3


def test_load_record_nonexistent_returns_none(db):
    assert memory_store.load_record(db, "nope") is None


# ── upsert semantics ───────────────────────────────────────────────────────────

def test_save_twice_updates_not_duplicates(db):
    s = _make_session("upsert")
    memory_store.save(db, s)

    s.turn_count = 5
    s.conversation_summary = "Turn 5"
    memory_store.save(db, s)

    total = db.query(CognitiveSessionRecord).count()
    assert total == 1
    record = memory_store.load_record(db, "upsert")
    assert record.turn_count == 5
    assert record.conversation_summary == "Turn 5"


# ── session without goal ───────────────────────────────────────────────────────

def test_save_session_without_goal(db):
    s = CognitiveSession(conversation_id="no-goal")
    s.turn_count = 1
    memory_store.save(db, s)

    restored = memory_store.load(db, "no-goal")
    assert restored is not None
    assert restored.active_goal is None
    assert restored.active_entities == {}
    assert restored.entity_order == []


# ── session without entities ───────────────────────────────────────────────────

def test_save_session_with_goal_no_entities(db):
    s = CognitiveSession(conversation_id="goal-only")
    s.active_goal = Goal(
        goal_id="g2",
        goal_text="Understand this page",
        status=GoalStatus.completed,
        created_at=datetime(2026, 3, 1),
        updated_at=datetime(2026, 3, 2),
    )
    memory_store.save(db, s)

    restored = memory_store.load(db, "goal-only")
    assert restored.active_goal is not None
    assert restored.active_goal.status == GoalStatus.completed
    assert restored.active_entities == {}
