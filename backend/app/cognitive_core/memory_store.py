"""
MemoryStore: persists CognitiveSession to and from the cognitive_sessions DB table.

Serialization format:
  entities_json   → JSON list of entity dicts
  entity_order_json → JSON list of entity ids (insertion order)
  goal_json       → JSON goal dict or NULL

All operations are synchronous. Callers obtain a Session from get_db() or
SessionLocal(). The MemoryStore itself has no state.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.cognitive_core.models import (
    CognitiveSession, Entity, EntityType, Goal, GoalStatus,
)
from app.models.db import CognitiveSessionRecord


# ── Serialization helpers ─────────────────────────────────────────────────────

def _entity_to_dict(e: Entity) -> dict:
    return {
        "id": e.id,
        "type": e.type.value,
        "name": e.name,
        "aliases": e.aliases,
        "metadata": e.metadata,
        "confidence": e.confidence,
        "source_turn": e.source_turn,
    }


def _dict_to_entity(d: dict) -> Entity:
    return Entity(
        id=d["id"],
        type=EntityType(d.get("type", "generic")),
        name=d["name"],
        aliases=d.get("aliases", []),
        metadata=d.get("metadata", {}),
        confidence=d.get("confidence", 1.0),
        source_turn=d.get("source_turn", 0),
    )


def _goal_to_dict(g: Goal) -> dict:
    return {
        "goal_id": g.goal_id,
        "goal_text": g.goal_text,
        "status": g.status.value,
        "subgoals": g.subgoals,
        "created_at": g.created_at.isoformat(),
        "updated_at": g.updated_at.isoformat(),
    }


def _dict_to_goal(d: dict) -> Goal:
    return Goal(
        goal_id=d["goal_id"],
        goal_text=d["goal_text"],
        status=GoalStatus(d.get("status", "active")),
        subgoals=d.get("subgoals", []),
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
    )


def _session_to_record(session: CognitiveSession) -> dict:
    """Convert CognitiveSession to a dict suitable for DB columns."""
    entities_list = [
        _entity_to_dict(e)
        for eid in session.entity_order
        if (e := session.active_entities.get(eid))
    ]
    return {
        "conversation_id": session.conversation_id,
        "turn_count": session.turn_count,
        "conversation_summary": session.conversation_summary,
        "active_intent": session.active_intent,
        "entities_json": json.dumps(entities_list),
        "entity_order_json": json.dumps(session.entity_order),
        "goal_json": json.dumps(_goal_to_dict(session.active_goal)) if session.active_goal else None,
        "updated_at": datetime.utcnow(),
    }


def _record_to_session(record: CognitiveSessionRecord) -> CognitiveSession:
    """Restore a CognitiveSession from a DB record."""
    session = CognitiveSession(
        conversation_id=record.conversation_id,
        turn_count=record.turn_count,
        conversation_summary=record.conversation_summary or "",
        active_intent=record.active_intent or "unknown",
        created_at=record.created_at or datetime.utcnow(),
        updated_at=record.updated_at or datetime.utcnow(),
    )

    # Restore entities
    entities_list: list[dict] = json.loads(record.entities_json or "[]")
    entity_order: list[str] = json.loads(record.entity_order_json or "[]")

    for d in entities_list:
        e = _dict_to_entity(d)
        session.active_entities[e.id] = e

    # Restore order (only include ids that exist in active_entities)
    session.entity_order = [eid for eid in entity_order if eid in session.active_entities]

    # Restore goal
    if record.goal_json:
        try:
            session.active_goal = _dict_to_goal(json.loads(record.goal_json))
        except (json.JSONDecodeError, KeyError):
            session.active_goal = None

    return session


# ── MemoryStore ───────────────────────────────────────────────────────────────

class MemoryStore:
    """Thin persistence wrapper. Stateless — create one per call site."""

    def save(self, db: Session, session: CognitiveSession) -> None:
        """Upsert CognitiveSession to DB."""
        fields = _session_to_record(session)
        record = db.get(CognitiveSessionRecord, session.conversation_id)
        if record is None:
            record = CognitiveSessionRecord(
                conversation_id=fields.pop("conversation_id"),
                created_at=datetime.utcnow(),
            )
            db.add(record)
        else:
            fields.pop("conversation_id", None)

        for key, val in fields.items():
            setattr(record, key, val)
        db.commit()

    def load(self, db: Session, conversation_id: str) -> Optional[CognitiveSession]:
        """Load and restore CognitiveSession from DB. Returns None if not found."""
        record = db.get(CognitiveSessionRecord, conversation_id)
        if record is None:
            return None
        return _record_to_session(record)

    def load_record(self, db: Session, conversation_id: str) -> Optional[CognitiveSessionRecord]:
        """Return the raw DB record (for inspection endpoints)."""
        return db.get(CognitiveSessionRecord, conversation_id)

    def all_conversation_ids(self, db: Session) -> list[str]:
        rows = db.query(CognitiveSessionRecord.conversation_id).all()
        return [r[0] for r in rows]


# Module-level singleton for convenience
_store = MemoryStore()


def save(db: Session, session: CognitiveSession) -> None:
    _store.save(db, session)


def load(db: Session, conversation_id: str) -> Optional[CognitiveSession]:
    return _store.load(db, conversation_id)


def load_record(db: Session, conversation_id: str) -> Optional[CognitiveSessionRecord]:
    return _store.load_record(db, conversation_id)
