"""
V5.0 Mission Layer — Mission Persistence.

Serializes Mission ↔ MissionRecord (ORM).

Mode flag (settings.mission_persistence):
  False (default) → all operations are no-ops → tests run without a DB
  True            → writes to the configured database

Session strategy: creates its own short-lived sessions via _session_scope().
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
from app.models.db import MissionRecord, MissionTaskRecord
from app.mission.models import Mission, MissionState

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
    return settings.mission_persistence


# ── Serialization helpers ─────────────────────────────────────────────────────

def _mission_to_fields(mission: Mission) -> dict:
    return {
        "mission_id":    mission.mission_id,
        "title":         mission.title,
        "objective":     mission.objective,
        "state":         mission.state.value,
        "priority":      mission.priority,
        "metadata_json": json.dumps(mission.metadata or {}),
        "updated_at":    mission.updated_at,
    }


def _record_to_mission(rec: MissionRecord) -> Mission:
    task_ids = [ref.task_id for ref in (rec.task_refs or [])]
    return Mission(
        mission_id=rec.mission_id,
        title=rec.title or "",
        objective=rec.objective or "",
        state=MissionState(rec.state),
        priority=rec.priority or 3,
        task_ids=task_ids,
        metadata=json.loads(rec.metadata_json or "{}"),
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def save(mission: Mission) -> None:
    """Upsert a Mission record + sync mission_tasks rows."""
    if not _enabled():
        return
    try:
        with _session_scope() as db:
            existing = db.get(MissionRecord, mission.mission_id)
            fields = _mission_to_fields(mission)
            if existing is None:
                rec = MissionRecord(**fields, created_at=mission.created_at)
                db.add(rec)
                db.flush()
            else:
                for k, v in fields.items():
                    setattr(existing, k, v)
                db.flush()

            # Sync mission_tasks: delete all then re-insert in order
            db.query(MissionTaskRecord).filter(
                MissionTaskRecord.mission_id == mission.mission_id
            ).delete()
            for pos, task_id in enumerate(mission.task_ids):
                db.add(MissionTaskRecord(
                    mission_id=mission.mission_id,
                    task_id=task_id,
                    position=pos,
                ))
    except Exception:
        logger.exception("mission.persistence.save failed for %s", mission.mission_id)


def load(mission_id: str) -> Optional[Mission]:
    """Load a mission from DB. Returns None when disabled or not found."""
    if not _enabled():
        return None
    try:
        with _session_scope() as db:
            rec = db.get(MissionRecord, mission_id)
            if rec is None:
                return None
            db.refresh(rec)
            return _record_to_mission(rec)
    except Exception:
        logger.exception("mission.persistence.load failed for %s", mission_id)
        return None


def load_active() -> list[Mission]:
    """Load all non-terminal missions. Used for in-memory warmup."""
    if not _enabled():
        return []
    terminal = {"COMPLETED", "FAILED", "ABANDONED"}
    try:
        with _session_scope() as db:
            recs = (
                db.query(MissionRecord)
                .filter(MissionRecord.state.notin_(terminal))
                .all()
            )
            result = []
            for rec in recs:
                db.refresh(rec)
                result.append(_record_to_mission(rec))
            return result
    except Exception:
        logger.exception("mission.persistence.load_active failed")
        return []


def delete(mission_id: str) -> bool:
    """Delete a mission and its task refs (CASCADE)."""
    if not _enabled():
        return False
    try:
        with _session_scope() as db:
            rec = db.get(MissionRecord, mission_id)
            if rec is None:
                return False
            db.delete(rec)
        return True
    except Exception:
        logger.exception("mission.persistence.delete failed for %s", mission_id)
        return False
