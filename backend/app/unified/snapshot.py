"""
V4.6 Unified Task Graph — TaskSnapshotSystem.

Creates lightweight context snapshots at key lifecycle milestones.
Snapshots are restoration accelerators — they store the key context
at a point in time so restoration does not need to replay the full event log.

Snapshot triggers (SNAPSHOT_TRIGGERS):
  research_complete    → after research pipeline finishes
  workflow_prepared    → after intelligence layer produces an execution plan
  workflow_started     → when workflow session begins
  workflow_completed   → after successful workflow execution

Safety: snapshots are read-only copies. They do NOT alter task state.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from contextlib import contextmanager
from typing import Optional

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.db import TaskSnapshotRecord
from app.unified.models import UnifiedTask

logger = logging.getLogger(__name__)

SNAPSHOT_TRIGGERS = {
    "research_complete",
    "workflow_prepared",
    "workflow_started",
    "workflow_completed",
}

_session_factory = None


def _set_session_factory(factory) -> None:
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


def _build_context(task: UnifiedTask) -> dict:
    """Extract the key context fields worth snapshotting."""
    return {
        "task_state":        task.state.value,
        "current_goal":      task.current_goal,
        "entities":          task.entities or {},
        "research_report":   task.research_report or {},
        "execution_plan":    task.execution_plan or {},
        "research_session_id": task.research_session_id,
        "workflow_session_id": task.workflow_session_id,
        "timeline_length":   len(task.timeline.events),
        "approval_count":    len(task.approvals),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def create(task: UnifiedTask, trigger: str) -> Optional[str]:
    """
    Create a snapshot at the given trigger milestone.
    Returns snapshot_id or None if disabled/trigger unknown.
    """
    if not _enabled():
        return None
    if trigger not in SNAPSHOT_TRIGGERS:
        return None
    # Timestamp-prefix ensures snapshot_ids are chronologically sortable,
    # giving deterministic ordering when two snapshots share a created_at second.
    snapshot_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{str(uuid.uuid4())[:4]}"
    context = _build_context(task)
    try:
        with _session_scope() as db:
            rec = TaskSnapshotRecord(
                snapshot_id=snapshot_id,
                task_id=task.task_id,
                trigger=trigger,
                task_state=task.state.value,
                context_json=json.dumps(context),
            )
            db.add(rec)
        # Increment counter on the parent task record
        from app.unified import persistence as task_persistence
        task_persistence.increment_snapshot_count(task.task_id)
        return snapshot_id
    except Exception:
        logger.exception("snapshot.create failed for task %s trigger %s", task.task_id, trigger)
        return None


def load_latest(task_id: str) -> Optional[dict]:
    """
    Load the most recent snapshot for a task.
    Returns the context dict or None if disabled/not found.
    """
    if not _enabled():
        return None
    try:
        with _session_scope() as db:
            row = (
                db.query(TaskSnapshotRecord)
                .filter(TaskSnapshotRecord.task_id == task_id)
                .order_by(TaskSnapshotRecord.snapshot_id.desc())
                .first()
            )
            if row is None:
                return None
            ctx = json.loads(row.context_json or "{}")
            ctx["snapshot_id"] = row.snapshot_id
            ctx["trigger"] = row.trigger
            ctx["created_at"] = row.created_at.isoformat()
            return ctx
    except Exception:
        logger.exception("snapshot.load_latest failed for task %s", task_id)
        return None


def load_all(task_id: str) -> list[dict]:
    """Load all snapshots for a task, newest first."""
    if not _enabled():
        return []
    try:
        with _session_scope() as db:
            rows = (
                db.query(TaskSnapshotRecord)
                .filter(TaskSnapshotRecord.task_id == task_id)
                .order_by(TaskSnapshotRecord.snapshot_id.desc())
                .all()
            )
            result = []
            for row in rows:
                ctx = json.loads(row.context_json or "{}")
                ctx.update({
                    "snapshot_id": row.snapshot_id,
                    "trigger":     row.trigger,
                    "task_state":  row.task_state,
                    "created_at":  row.created_at.isoformat(),
                })
                result.append(ctx)
            return result
    except Exception:
        logger.exception("snapshot.load_all failed for task %s", task_id)
        return []


def count(task_id: str) -> int:
    """Count snapshots for a task."""
    if not _enabled():
        return 0
    try:
        with _session_scope() as db:
            return (
                db.query(TaskSnapshotRecord)
                .filter(TaskSnapshotRecord.task_id == task_id)
                .count()
            )
    except Exception:
        return 0
