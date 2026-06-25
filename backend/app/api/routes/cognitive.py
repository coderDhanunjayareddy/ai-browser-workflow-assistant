"""
V3.0 Cognitive REST endpoints — inspection and maintenance.

GET  /cognitive/state/{conversation_id}  — full session state for debugging
POST /cognitive/cleanup                   — delete sessions older than N days
GET  /cognitive/analytics                 — combined cognitive + memory analytics
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/cognitive", tags=["cognitive"])


# ── Request / Response schemas ─────────────────────────────────────────────────

class CleanupRequest(BaseModel):
    retention_days: int = 30


class CleanupResponse(BaseModel):
    deleted: int
    retained: int
    retention_days: int


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/state/{conversation_id}")
def get_cognitive_state(conversation_id: str, db: Session = Depends(get_db)) -> dict:
    """
    Return the persisted cognitive session for a conversation.
    Returns 404 if no record exists for that conversation_id.
    """
    from app.cognitive_core import memory_store
    record = memory_store.load_record(db, conversation_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cognitive session found for conversation_id={conversation_id!r}",
        )
    import json
    return {
        "conversation_id": record.conversation_id,
        "turn_count": record.turn_count,
        "active_intent": record.active_intent,
        "conversation_summary": record.conversation_summary,
        "entities": json.loads(record.entities_json or "[]"),
        "entity_order": json.loads(record.entity_order_json or "[]"),
        "goal": json.loads(record.goal_json) if record.goal_json else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


@router.post("/cleanup", response_model=CleanupResponse)
def cleanup_sessions(body: CleanupRequest, db: Session = Depends(get_db)) -> CleanupResponse:
    """
    Delete cognitive sessions not updated within `retention_days`.
    Returns a summary of deleted vs. retained session counts.
    """
    from app.cognitive_core.memory_cleanup import cleanup_old_sessions, count_sessions
    stats = cleanup_old_sessions(db, retention_days=body.retention_days)
    remaining = count_sessions(db)
    return CleanupResponse(
        deleted=stats["deleted_sessions"],
        retained=remaining["total_sessions"],
        retention_days=body.retention_days,
    )


@router.get("/analytics")
def get_analytics(db: Session = Depends(get_db)) -> dict:
    """
    Combined cognitive analytics: in-memory session stats + memory store DB counts.
    """
    from app.cognitive_core import conversation_manager as cognitive_manager
    from app.cognitive_core.memory_cleanup import count_sessions
    from app.cognitive_core.analytics import get_cognitive_analytics

    in_memory = cognitive_manager.get_analytics()
    db_counts = count_sessions(db)
    turn_analytics = get_cognitive_analytics()

    return {
        "in_memory": in_memory,
        "database": db_counts,
        "turn_analytics": turn_analytics,
    }
