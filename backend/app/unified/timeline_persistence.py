"""
V4.6 Unified Task Graph — TimelinePersistence.

Persists individual timeline events to TaskTimelineRecord rows.
Reconstructs a TaskTimeline from DB rows on restoration.
No-op when persistence is disabled.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Optional

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.db import TaskTimelineRecord
from app.unified.models import TimelineEvent, TimelineEventType, TaskTimeline

logger = logging.getLogger(__name__)

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


# ── Public API ────────────────────────────────────────────────────────────────

def save_event(event: TimelineEvent) -> None:
    """Persist a single timeline event. No-op when disabled."""
    if not _enabled():
        return
    try:
        with _session_scope() as db:
            existing = db.get(TaskTimelineRecord, event.event_id)
            if existing is None:
                rec = TaskTimelineRecord(
                    event_id=event.event_id,
                    task_id=event.task_id,
                    event_type=event.event_type.value,
                    payload_json=json.dumps(event.data),
                    timestamp=event.timestamp,
                )
                db.add(rec)
    except Exception:
        logger.exception("timeline_persistence.save_event failed for %s", event.event_id)


def save_timeline(timeline: TaskTimeline) -> None:
    """Persist all events in a timeline (idempotent — skips existing event_ids)."""
    if not _enabled():
        return
    for event in timeline.events:
        save_event(event)


def load_timeline(task_id: str) -> TaskTimeline:
    """Reconstruct a TaskTimeline from persisted rows. Returns empty timeline if disabled/not found."""
    tl = TaskTimeline(task_id=task_id)
    if not _enabled():
        return tl
    try:
        with _session_scope() as db:
            rows = (
                db.query(TaskTimelineRecord)
                .filter(TaskTimelineRecord.task_id == task_id)
                .order_by(TaskTimelineRecord.timestamp)
                .all()
            )
            for row in rows:
                try:
                    event_type = TimelineEventType(row.event_type)
                    payload = json.loads(row.payload_json or "{}")
                    event = TimelineEvent(
                        event_id=row.event_id,
                        event_type=event_type,
                        task_id=task_id,
                        data=payload,
                        timestamp=row.timestamp,
                    )
                    tl.events.append(event)
                except Exception:
                    pass  # skip rows with unknown event types
    except Exception:
        logger.exception("timeline_persistence.load_timeline failed for task %s", task_id)
    return tl


def delete_events(task_id: str) -> int:
    """Delete all timeline events for a task. Returns count deleted."""
    if not _enabled():
        return 0
    try:
        with _session_scope() as db:
            count = (
                db.query(TaskTimelineRecord)
                .filter(TaskTimelineRecord.task_id == task_id)
                .count()
            )
            db.query(TaskTimelineRecord).filter(
                TaskTimelineRecord.task_id == task_id
            ).delete()
            return count
    except Exception:
        logger.exception("timeline_persistence.delete_events failed for task %s", task_id)
        return 0
