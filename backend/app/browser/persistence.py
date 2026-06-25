"""
V7.0 Live Browser Sync Layer — BrowserEventPersistence.

Optional persistence flag, disabled by default.
Follows V4.6 pattern: feature flag controls DB writes; memory store is always active.

When BROWSER_EVENT_PERSISTENCE = False (default):
  - All storage is in-memory via BrowserEventRegistry
  - No DB writes

When BROWSER_EVENT_PERSISTENCE = True:
  - Events are saved to the SQLite DB (stub implementation)
  - Registry continues to serve hot cache reads
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.browser.models import BrowserEvent

# Feature flag — disabled by default (V4.6 pattern)
BROWSER_EVENT_PERSISTENCE: bool = False


class BrowserEventPersistence:

    def __init__(self, enabled: bool = BROWSER_EVENT_PERSISTENCE) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def save(self, event: "BrowserEvent") -> None:
        if not self._enabled:
            return
        # Stub: when enabled, persist event to DB using SQLAlchemy session
        # from app.core.database import SessionLocal
        # with SessionLocal() as session:
        #     session.add(BrowserEventORM(**event.to_dict()))
        #     session.commit()

    def load_for_mission(self, mission_id: str) -> list["BrowserEvent"]:
        if not self._enabled:
            return []
        # Stub: when enabled, load from DB
        # from app.core.database import SessionLocal
        # with SessionLocal() as session:
        #     rows = session.query(BrowserEventORM).filter_by(mission_id=mission_id).all()
        #     return [BrowserEvent(**row.__dict__) for row in rows]
        return []

    def load_for_tab(self, tab_id: str) -> list["BrowserEvent"]:
        if not self._enabled:
            return []
        return []

    def delete_for_mission(self, mission_id: str) -> int:
        """Returns number of events deleted. No-op when disabled."""
        if not self._enabled:
            return 0
        return 0


# ── Module-level singleton ────────────────────────────────────────────────────

_persistence = BrowserEventPersistence()


def save(event: "BrowserEvent") -> None:
    _persistence.save(event)

def load_for_mission(mission_id: str) -> list["BrowserEvent"]:
    return _persistence.load_for_mission(mission_id)

def is_enabled() -> bool:
    return _persistence.enabled
