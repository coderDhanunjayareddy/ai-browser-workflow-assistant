"""
ResearchSessionManager: in-memory multi-turn research session store.

One ResearchSession per conversation_id. Sessions are keyed by (conversation_id, topic)
so a new research query within the same conversation creates a new session.
V3.6 will add SQLAlchemy persistence following the CognitiveSession pattern from V3.0.
"""
from __future__ import annotations

import uuid
import threading
from datetime import datetime
from typing import Optional

from app.research.models import (
    ResearchSession, ResearchPlan, ResearchReport,
    ResearchSource, ResearchStatus,
)

_lock = threading.Lock()
_sessions: dict[str, ResearchSession] = {}  # session_id → session
_by_conversation: dict[str, str] = {}       # conversation_id → latest session_id


def _now() -> datetime:
    return datetime.utcnow()


def create_session(conversation_id: str, topic: str, goal_id: Optional[str] = None) -> ResearchSession:
    """Create a new ResearchSession and register it as the active session for this conversation."""
    session = ResearchSession(
        session_id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        topic=topic,
        goal_id=goal_id,
        created_at=_now(),
        updated_at=_now(),
    )
    with _lock:
        _sessions[session.session_id] = session
        _by_conversation[conversation_id] = session.session_id
    return session


def get_active(conversation_id: str) -> Optional[ResearchSession]:
    """Return the most recent active ResearchSession for this conversation, or None."""
    with _lock:
        sid = _by_conversation.get(conversation_id)
        if sid is None:
            return None
        return _sessions.get(sid)


def get_session(session_id: str) -> Optional[ResearchSession]:
    with _lock:
        return _sessions.get(session_id)


def attach_plan(session: ResearchSession, plan: ResearchPlan) -> None:
    with _lock:
        session.plan = plan
        session.updated_at = _now()


def add_sources(session: ResearchSession, sources: list[ResearchSource]) -> None:
    """Append new sources, deduplicating by URL (empty URL sources are always added)."""
    with _lock:
        existing_urls = {s.url for s in session.sources if s.url}
        for src in sources:
            if src.url and src.url in existing_urls:
                continue
            session.sources.append(src)
            if src.url:
                existing_urls.add(src.url)
        session.updated_at = _now()


def attach_report(session: ResearchSession, report: ResearchReport) -> None:
    with _lock:
        session.report = report
        session.status = ResearchStatus.completed
        session.synthesis_count += 1
        session.updated_at = _now()


def mark_failed(session: ResearchSession) -> None:
    with _lock:
        session.status = ResearchStatus.failed
        session.updated_at = _now()


def list_sessions() -> list[ResearchSession]:
    with _lock:
        return list(_sessions.values())


def count_sessions() -> int:
    with _lock:
        return len(_sessions)


def _reset_for_testing() -> None:
    """Clear all in-memory state. For tests only."""
    global _sessions, _by_conversation
    with _lock:
        _sessions = {}
        _by_conversation = {}
