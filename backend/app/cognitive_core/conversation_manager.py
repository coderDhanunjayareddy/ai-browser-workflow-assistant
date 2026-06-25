"""
CognitiveConversationManager: orchestrates the Cognitive Core per conversation.

V3.0 adds transparent DB persistence:
  - get_or_create(): checks in-memory, then DB (restore on cache-miss), then creates new
  - process_turn():  updates in-memory state + saves to DB if db is provided

All persistence is optional — pass db=None to skip (used in tests and fast paths
that haven't yet been wired to a DB session).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.cognitive_core.models import CognitiveSession, Entity, Goal
from app.cognitive_core import entity_registry, goal_tracker

MAX_SESSIONS = 100
_skip_persistence = False  # set True by _reset_for_testing() to isolate unit tests


class CognitiveConversationManager:
    def __init__(self) -> None:
        self._sessions: dict[str, CognitiveSession] = {}
        self._insertion_order: list[str] = []
        self._restored_count: int = 0
        self._persisted_count: int = 0

    def get_or_create(
        self,
        conversation_id: str,
        db: Optional[Session] = None,
    ) -> CognitiveSession:
        # 1. In-memory cache
        if conversation_id in self._sessions:
            return self._sessions[conversation_id]

        # 2. Try to restore from DB (V3.0 memory restore)
        if db is not None and not _skip_persistence:
            from app.cognitive_core import memory_store
            restored = memory_store.load(db, conversation_id)
            if restored is not None:
                self._register(restored)
                self._restored_count += 1
                return restored

        # 3. Create new session
        session = CognitiveSession(conversation_id=conversation_id)
        self._register(session)
        return session

    def _register(self, session: CognitiveSession) -> None:
        if len(self._sessions) >= MAX_SESSIONS:
            oldest = self._insertion_order.pop(0)
            self._sessions.pop(oldest, None)
        self._sessions[session.conversation_id] = session
        self._insertion_order.append(session.conversation_id)

    def process_turn(
        self,
        session: CognitiveSession,
        *,
        intent: str,
        message: str,
        summary_entities: Optional[list[dict]] = None,
        response_type: str,
        handoff_triggered: bool = False,
        db: Optional[Session] = None,
    ) -> list[Entity]:
        """
        Update cognitive state for one completed turn.
        Persists to DB if `db` is provided.
        Returns the list of newly extracted entities (deduped by id).
        """
        session.turn_count += 1
        session.active_intent = intent
        session.updated_at = datetime.utcnow()

        # Extract entities
        new_entities: list[Entity] = []
        turn_number = session.turn_count

        if summary_entities:
            new_entities.extend(
                entity_registry.extract_from_summary_entities(
                    session, summary_entities, turn=turn_number
                )
            )

        new_entities.extend(
            entity_registry.extract_from_message(session, message, turn=turn_number)
        )

        seen: set[str] = set()
        deduped: list[Entity] = []
        for e in new_entities:
            if e.id not in seen:
                seen.add(e.id)
                deduped.append(e)
        new_entities = deduped

        # Update goal
        goal_tracker.evolve_goal(
            session,
            intent=intent,
            message=message,
            entities=entity_registry.get_ordered_entities(session),
            response_type=response_type,
            handoff_triggered=handoff_triggered,
        )

        # Update conversation summary
        session.conversation_summary = _build_summary(session)

        # Persist to DB (V3.0)
        if db is not None and not _skip_persistence:
            from app.cognitive_core import memory_store
            memory_store.save(db, session)
            self._persisted_count += 1

        return new_entities

    def get_session(self, conversation_id: str) -> Optional[CognitiveSession]:
        return self._sessions.get(conversation_id)

    def clear(self) -> None:
        self._sessions.clear()
        self._insertion_order.clear()
        self._restored_count = 0
        self._persisted_count = 0

    # ── Analytics ─────────────────────────────────────────────────────────────

    def active_session_count(self) -> int:
        return len(self._sessions)

    def total_entity_count(self) -> int:
        return sum(len(s.active_entities) for s in self._sessions.values())

    def goal_status_summary(self) -> dict[str, int]:
        statuses = [
            s.active_goal.status.value
            for s in self._sessions.values()
            if s.active_goal
        ]
        return dict(Counter(statuses))

    def restored_count(self) -> int:
        return self._restored_count

    def persisted_count(self) -> int:
        return self._persisted_count


def _build_summary(session: CognitiveSession) -> str:
    parts: list[str] = []
    entities = entity_registry.get_ordered_entities(session)
    if entities:
        names = ", ".join(e.name for e in entities[:3])
        suffix = f" (+{len(entities) - 3} more)" if len(entities) > 3 else ""
        parts.append(f"Discussing: {names}{suffix}")
    if session.active_goal:
        parts.append(f"Goal: {session.active_goal.goal_text}")
    parts.append(f"Turn {session.turn_count}")
    return ". ".join(parts)


# ── Module-level singleton ────────────────────────────────────────────────────

_manager = CognitiveConversationManager()


def get_or_create(
    conversation_id: str,
    db: Optional[Session] = None,
) -> CognitiveSession:
    return _manager.get_or_create(conversation_id, db=db)


def process_turn(
    session: CognitiveSession,
    *,
    intent: str,
    message: str,
    summary_entities: Optional[list[dict]] = None,
    response_type: str,
    handoff_triggered: bool = False,
    db: Optional[Session] = None,
) -> list[Entity]:
    return _manager.process_turn(
        session,
        intent=intent,
        message=message,
        summary_entities=summary_entities,
        response_type=response_type,
        handoff_triggered=handoff_triggered,
        db=db,
    )


def get_session(conversation_id: str) -> Optional[CognitiveSession]:
    return _manager.get_session(conversation_id)


def get_analytics() -> dict:
    return {
        "active_sessions": _manager.active_session_count(),
        "total_entities": _manager.total_entity_count(),
        "goal_statuses": _manager.goal_status_summary(),
        "persisted_sessions": _manager.persisted_count(),
        "restored_sessions": _manager.restored_count(),
    }


def _reset_for_testing() -> None:
    global _skip_persistence
    _skip_persistence = True
    _manager.clear()
