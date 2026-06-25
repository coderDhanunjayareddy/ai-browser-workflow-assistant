"""
V7.5 Decision Center — DecisionPersistence.

V4.6 feature flag pattern: disabled by default.
When enabled (future): persist DecisionItems to DB via SQLAlchemy.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.decisions.models import DecisionItem

# Feature flag (V4.6 pattern)
DECISION_PERSISTENCE: bool = False


class DecisionPersistence:

    def __init__(self, enabled: bool = DECISION_PERSISTENCE) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def save(self, item: "DecisionItem") -> None:
        if not self._enabled:
            return
        # Stub: SQLAlchemy write when enabled
        # from app.core.database import SessionLocal
        # with SessionLocal() as session:
        #     session.add(DecisionItemORM(**item.to_dict()))
        #     session.commit()

    def load_for_mission(self, mission_id: str) -> list["DecisionItem"]:
        if not self._enabled:
            return []
        return []

    def delete_for_mission(self, mission_id: str) -> int:
        if not self._enabled:
            return 0
        return 0


# Module-level singleton
_persistence = DecisionPersistence()


def save(item: "DecisionItem") -> None:
    _persistence.save(item)

def load_for_mission(mission_id: str) -> list["DecisionItem"]:
    return _persistence.load_for_mission(mission_id)

def is_enabled() -> bool:
    return _persistence.enabled
