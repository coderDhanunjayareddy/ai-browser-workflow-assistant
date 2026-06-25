"""
V7.5 Decision Center — DecisionFeed.

Filtered views over the DecisionRegistry.
All reads are non-mutating. No state changes here.
"""
from __future__ import annotations

from typing import Optional

from app.decisions.models import DecisionItem, DecisionPriority, DecisionStatus
import app.decisions.registry as reg


class DecisionFeed:

    def latest(self, limit: int = 20) -> list[DecisionItem]:
        """All decisions sorted newest first."""
        items = reg.list_all(limit=limit * 2)
        items.sort(key=lambda d: d.created_at, reverse=True)
        return items[:limit]

    def active(self, mission_id: Optional[str] = None, limit: int = 50) -> list[DecisionItem]:
        """OPEN decisions only, highest priority first."""
        return reg.list_active(mission_id=mission_id, limit=limit)

    def critical_only(self, limit: int = 20) -> list[DecisionItem]:
        """CRITICAL priority decisions, newest first."""
        items = reg.list_critical(limit=limit * 2)
        items.sort(key=lambda d: d.created_at, reverse=True)
        return items[:limit]

    def for_mission(self, mission_id: str, limit: int = 100) -> list[DecisionItem]:
        """All decisions for a mission, priority-sorted."""
        return reg.list_for_mission(mission_id, limit=limit)

    def for_source(self, source: str, limit: int = 50) -> list[DecisionItem]:
        """Decisions from a specific source component."""
        all_items = reg.list_all(limit=1000)
        filtered  = [d for d in all_items if d.source == source]
        return filtered[:limit]

    def by_status(self, status: DecisionStatus, limit: int = 50) -> list[DecisionItem]:
        all_items = reg.list_all(limit=1000)
        return [d for d in all_items if d.status == status][:limit]

    def by_priority(self, priority: DecisionPriority, limit: int = 50) -> list[DecisionItem]:
        all_items = reg.list_all(limit=1000)
        return [d for d in all_items if d.priority == priority][:limit]

    def summary_for_mission(self, mission_id: str) -> dict:
        items   = self.for_mission(mission_id)
        active  = [d for d in items if d.is_active]
        critical= [d for d in active if d.priority == DecisionPriority.critical]
        return {
            "total_decisions":    len(items),
            "active_decisions":   len(active),
            "critical_decisions": len(critical),
            "recent_decisions":   [d.to_dict() for d in items[:5]],
        }


# Module-level singleton
_feed = DecisionFeed()


def latest(limit: int = 20) -> list[DecisionItem]:
    return _feed.latest(limit)

def active(mission_id: Optional[str] = None, limit: int = 50) -> list[DecisionItem]:
    return _feed.active(mission_id, limit)

def critical_only(limit: int = 20) -> list[DecisionItem]:
    return _feed.critical_only(limit)

def for_mission(mission_id: str, limit: int = 100) -> list[DecisionItem]:
    return _feed.for_mission(mission_id, limit)

def for_source(source: str, limit: int = 50) -> list[DecisionItem]:
    return _feed.for_source(source, limit)

def summary_for_mission(mission_id: str) -> dict:
    return _feed.summary_for_mission(mission_id)
