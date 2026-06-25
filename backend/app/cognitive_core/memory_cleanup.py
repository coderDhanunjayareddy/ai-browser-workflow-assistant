"""
MemoryCleanup: bounded retention for cognitive session records.

Prunes cognitive_sessions rows older than `retention_days`.
Triggered manually via POST /cognitive/cleanup — no background scheduler in V3.0.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.db import CognitiveSessionRecord

DEFAULT_RETENTION_DAYS = 30


def cleanup_old_sessions(db: Session, retention_days: int = DEFAULT_RETENTION_DAYS) -> dict:
    """
    Delete CognitiveSessionRecord rows not updated within `retention_days`.
    Returns a summary dict with cleanup stats.
    """
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    old_records = (
        db.query(CognitiveSessionRecord)
        .filter(CognitiveSessionRecord.updated_at < cutoff)
        .all()
    )
    count = len(old_records)
    for record in old_records:
        db.delete(record)
    db.commit()
    return {
        "deleted_sessions": count,
        "retention_days": retention_days,
        "cutoff_utc": cutoff.isoformat(),
    }


def count_sessions(db: Session) -> dict:
    """Return counts of total and old (>30d) cognitive sessions."""
    total = db.query(CognitiveSessionRecord).count()
    cutoff = datetime.utcnow() - timedelta(days=DEFAULT_RETENTION_DAYS)
    old = db.query(CognitiveSessionRecord).filter(
        CognitiveSessionRecord.updated_at < cutoff
    ).count()
    return {"total_sessions": total, "old_sessions": old}
