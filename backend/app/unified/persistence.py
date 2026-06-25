"""
V4.6 Unified Task Graph — UnifiedTaskPersistence.

Serializes UnifiedTask ↔ UnifiedTaskRecord (ORM).

Mode flag (settings.unified_task_persistence):
  False (default) → all operations are no-ops → tests run without a DB
  True            → writes to the configured database after every state change

Session strategy: creates its own short-lived sessions so callers
(lifecycle manager, approval center) do not need to inject a DB session.
A custom session factory can be injected via _set_session_factory() for tests.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.db import UnifiedTaskRecord
from app.unified.models import (
    UnifiedTask, TaskState, ApprovalStatus,
)

logger = logging.getLogger(__name__)

# ── Session factory (overridable for tests) ───────────────────────────────────

_session_factory = None


def _set_session_factory(factory) -> None:
    """Inject a custom session factory for testing."""
    global _session_factory
    _session_factory = factory


def _reset_session_factory() -> None:
    global _session_factory
    _session_factory = None


@contextmanager
def _session_scope():
    factory = _session_factory or SessionLocal
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _enabled() -> bool:
    return settings.unified_task_persistence


# ── Serialization helpers ─────────────────────────────────────────────────────

def _task_to_record(task: UnifiedTask) -> dict:
    return {
        "task_id":                  task.task_id,
        "conversation_id":          task.conversation_id,
        "cognitive_session_id":     task.cognitive_session_id,
        "research_session_id":      task.research_session_id,
        "workflow_session_id":      task.workflow_session_id,
        "original_query":           task.original_query or "",
        "current_goal":             task.current_goal,
        "state":                    task.state.value,
        "approval_state":           task.approval_state.value,
        "entities_json":            json.dumps(task.entities or {}),
        "execution_plan_json":      json.dumps(task.execution_plan) if task.execution_plan else None,
        "research_report_json":     json.dumps(task.research_report) if task.research_report else None,
        "updated_at":               task.updated_at,
    }


def _record_to_task(rec: UnifiedTaskRecord) -> UnifiedTask:
    """Reconstruct a UnifiedTask from an ORM record (metadata only, no timeline/approvals)."""
    from app.unified.models import TaskTimeline

    state = TaskState(rec.state)
    approval_st = ApprovalStatus(rec.approval_state)

    task = UnifiedTask(
        task_id=rec.task_id,
        conversation_id=rec.conversation_id,
        cognitive_session_id=rec.cognitive_session_id,
        research_session_id=rec.research_session_id,
        workflow_session_id=rec.workflow_session_id,
        original_query=rec.original_query or "",
        current_goal=rec.current_goal,
        state=state,
        approval_state=approval_st,
        entities=json.loads(rec.entities_json or "{}"),
        execution_plan=json.loads(rec.execution_plan_json) if rec.execution_plan_json else None,
        research_report=json.loads(rec.research_report_json) if rec.research_report_json else None,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )
    # Force the state_history to start with the current state
    task.state_history = [(state, rec.updated_at)]
    task.timeline = TaskTimeline(task_id=rec.task_id)
    return task


# ── Public API ────────────────────────────────────────────────────────────────

def save(task: UnifiedTask) -> None:
    """Upsert a UnifiedTask to the database. No-op when persistence is disabled."""
    if not _enabled():
        return
    try:
        with _session_scope() as db:
            existing = db.get(UnifiedTaskRecord, task.task_id)
            fields = _task_to_record(task)
            if existing is None:
                rec = UnifiedTaskRecord(
                    **fields,
                    created_at=task.created_at,
                    snapshot_count=0,
                )
                db.add(rec)
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
    except Exception:
        logger.exception("persistence.save failed for task %s", task.task_id)


def load(task_id: str) -> Optional[UnifiedTask]:
    """Load a task's metadata from DB. Returns None when persistence is disabled or not found."""
    if not _enabled():
        return None
    try:
        with _session_scope() as db:
            rec = db.get(UnifiedTaskRecord, task_id)
            if rec is None:
                return None
            return _record_to_task(rec)
    except Exception:
        logger.exception("persistence.load failed for task %s", task_id)
        return None


def load_by_conversation(conversation_id: str) -> Optional[UnifiedTask]:
    """Load a task by conversation_id. Returns None when not found or disabled."""
    if not _enabled():
        return None
    try:
        with _session_scope() as db:
            rec = (
                db.query(UnifiedTaskRecord)
                .filter(UnifiedTaskRecord.conversation_id == conversation_id)
                .order_by(UnifiedTaskRecord.created_at.desc())
                .first()
            )
            if rec is None:
                return None
            return _record_to_task(rec)
    except Exception:
        logger.exception("persistence.load_by_conversation failed for %s", conversation_id)
        return None


def load_active() -> list[UnifiedTask]:
    """Load all non-terminal tasks for in-memory warmup."""
    if not _enabled():
        return []
    terminal = {"COMPLETED", "ABANDONED"}
    try:
        with _session_scope() as db:
            recs = (
                db.query(UnifiedTaskRecord)
                .filter(UnifiedTaskRecord.state.notin_(terminal))
                .all()
            )
            return [_record_to_task(r) for r in recs]
    except Exception:
        logger.exception("persistence.load_active failed")
        return []


def delete(task_id: str) -> bool:
    """Delete a task record (and cascades: timeline, approvals, snapshots)."""
    if not _enabled():
        return False
    try:
        with _session_scope() as db:
            rec = db.get(UnifiedTaskRecord, task_id)
            if rec is None:
                return False
            db.delete(rec)
        return True
    except Exception:
        logger.exception("persistence.delete failed for task %s", task_id)
        return False


def mark_restored(task_id: str) -> None:
    """Stamp restored_at on a task record."""
    if not _enabled():
        return
    try:
        with _session_scope() as db:
            rec = db.get(UnifiedTaskRecord, task_id)
            if rec:
                rec.restored_at = datetime.utcnow()
    except Exception:
        logger.exception("persistence.mark_restored failed for task %s", task_id)


def increment_snapshot_count(task_id: str) -> None:
    """Increment snapshot_count on the task record."""
    if not _enabled():
        return
    try:
        with _session_scope() as db:
            rec = db.get(UnifiedTaskRecord, task_id)
            if rec:
                rec.snapshot_count = (rec.snapshot_count or 0) + 1
                rec.updated_at = datetime.utcnow()
    except Exception:
        logger.exception("persistence.increment_snapshot_count failed for %s", task_id)
