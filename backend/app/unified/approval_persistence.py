"""
V4.6 Unified Task Graph — ApprovalPersistence.

Persists ApprovalRecord objects to TaskApprovalRecord rows.
Reconstructs approval lists on restoration.
No-op when persistence is disabled.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from app.core.database import SessionLocal
from app.core.config import settings
from app.models.db import TaskApprovalRecord
from app.unified.models import ApprovalRecord, ApprovalStatus

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


# ── Serialization ─────────────────────────────────────────────────────────────

def _to_record(rec: ApprovalRecord) -> dict:
    return {
        "approval_id":     rec.approval_id,
        "task_id":         rec.task_id,
        "action":          rec.action,
        "risk_level":      rec.risk_level,
        "status":          rec.status.value,
        "resolution_note": rec.resolution_note or "",
        "created_at":      rec.created_at,
        "resolved_at":     rec.resolved_at,
    }


def _from_record(row: TaskApprovalRecord) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=row.approval_id,
        task_id=row.task_id,
        action=row.action,
        risk_level=row.risk_level,
        status=ApprovalStatus(row.status),
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        resolution_note=row.resolution_note or "",
    )


# ── Public API ────────────────────────────────────────────────────────────────

def save(rec: ApprovalRecord) -> None:
    """Upsert an approval record. No-op when disabled."""
    if not _enabled():
        return
    try:
        with _session_scope() as db:
            existing = db.get(TaskApprovalRecord, rec.approval_id)
            fields = _to_record(rec)
            if existing is None:
                db.add(TaskApprovalRecord(**fields))
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
    except Exception:
        logger.exception("approval_persistence.save failed for %s", rec.approval_id)


def load_all(task_id: str) -> list[ApprovalRecord]:
    """Load all approval records for a task. Returns [] when disabled or not found."""
    if not _enabled():
        return []
    try:
        with _session_scope() as db:
            rows = (
                db.query(TaskApprovalRecord)
                .filter(TaskApprovalRecord.task_id == task_id)
                .order_by(TaskApprovalRecord.created_at)
                .all()
            )
            return [_from_record(r) for r in rows]
    except Exception:
        logger.exception("approval_persistence.load_all failed for task %s", task_id)
        return []


def delete_all(task_id: str) -> int:
    """Delete all approval records for a task."""
    if not _enabled():
        return 0
    try:
        with _session_scope() as db:
            count = (
                db.query(TaskApprovalRecord)
                .filter(TaskApprovalRecord.task_id == task_id)
                .count()
            )
            db.query(TaskApprovalRecord).filter(
                TaskApprovalRecord.task_id == task_id
            ).delete()
            return count
    except Exception:
        logger.exception("approval_persistence.delete_all failed for task %s", task_id)
        return 0
