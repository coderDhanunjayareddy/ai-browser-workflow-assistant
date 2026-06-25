"""
V7.5 Decision Center — DecisionRegistry.

In-memory store for DecisionItems.
Indexed by decision_id (primary) and mission_id (secondary).
TTL = 3600s — decisions persist longer than cache entries.
RLock + monotonic pattern from V6.5/V7.0.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

from app.decisions.models import (
    DecisionItem, DecisionStatus, DecisionPriority, PRIORITY_ORDER,
)

TTL_SECONDS: int = 3600   # 1 hour; decisions are long-lived advisory items


class DecisionRegistry:

    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        # decision_id → (DecisionItem, inserted_at)
        self._items: dict[str, tuple[DecisionItem, float]] = {}
        # mission_id → set[decision_id]
        self._by_mission: dict[str, set[str]] = defaultdict(set)
        self._total_added:   int = 0
        self._total_evicted: int = 0

    def _is_expired(self, inserted_at: float, now: float) -> bool:
        return now - inserted_at > self._ttl

    def add(self, item: DecisionItem) -> None:
        now = time.monotonic()
        with self._lock:
            self._items[item.decision_id] = (item, now)
            if item.mission_id:
                self._by_mission[item.mission_id].add(item.decision_id)
            self._total_added += 1

    def get(self, decision_id: str) -> Optional[DecisionItem]:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(decision_id)
            if entry is None:
                return None
            item, inserted_at = entry
            if self._is_expired(inserted_at, now):
                self._evict(decision_id, item)
                return None
            return item

    def _evict(self, decision_id: str, item: DecisionItem) -> None:
        self._items.pop(decision_id, None)
        if item.mission_id:
            self._by_mission[item.mission_id].discard(decision_id)
        self._total_evicted += 1

    def update_status(self, decision_id: str, status: DecisionStatus) -> bool:
        now_dt = datetime.utcnow()
        with self._lock:
            entry = self._items.get(decision_id)
            if entry is None:
                return False
            item, inserted_at = entry
            item.status = status
            if status == DecisionStatus.acknowledged:
                item.acknowledged_at = now_dt
            elif status == DecisionStatus.resolved:
                item.resolved_at = now_dt
            elif status == DecisionStatus.dismissed:
                item.dismissed_at = now_dt
            return True

    def list_all(self, limit: int = 100) -> list[DecisionItem]:
        now = time.monotonic()
        with self._lock:
            valid = [
                item for item, inserted_at in self._items.values()
                if not self._is_expired(inserted_at, now)
            ]
        valid.sort(key=lambda d: (-d.priority_order, d.created_at.isoformat()), reverse=False)
        valid.sort(key=lambda d: d.priority_order, reverse=True)
        return valid[:limit]

    def list_for_mission(self, mission_id: str, limit: int = 100) -> list[DecisionItem]:
        now = time.monotonic()
        with self._lock:
            ids  = self._by_mission.get(mission_id, set()).copy()
            out  = []
            for did in ids:
                entry = self._items.get(did)
                if entry is None:
                    continue
                item, inserted_at = entry
                if self._is_expired(inserted_at, now):
                    self._evict(did, item)
                    continue
                out.append(item)
        out.sort(key=lambda d: d.priority_order, reverse=True)
        return out[:limit]

    def list_active(self, mission_id: Optional[str] = None, limit: int = 100) -> list[DecisionItem]:
        items = (self.list_for_mission(mission_id) if mission_id
                 else self.list_all(limit=1000))
        return [d for d in items if d.is_active][:limit]

    def list_critical(self, limit: int = 50) -> list[DecisionItem]:
        return [d for d in self.list_all(limit=1000)
                if d.priority == DecisionPriority.critical][:limit]

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(
                1 for _, inserted_at in self._items.values()
                if not self._is_expired(inserted_at, now)
            )

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            valid = [(item, ins) for item, ins in self._items.values()
                     if not self._is_expired(ins, now)]
        return {
            "cached_items":   len(valid),
            "total_added":    self._total_added,
            "total_evicted":  self._total_evicted,
            "open_count":     sum(1 for i, _ in valid if i.status == DecisionStatus.open),
        }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._items.clear()
            self._by_mission.clear()
            self._total_added   = 0
            self._total_evicted = 0


# Module-level singleton
_registry = DecisionRegistry()


def add(item: DecisionItem) -> None:
    _registry.add(item)

def get(decision_id: str) -> Optional[DecisionItem]:
    return _registry.get(decision_id)

def update_status(decision_id: str, status: DecisionStatus) -> bool:
    return _registry.update_status(decision_id, status)

def list_all(limit: int = 100) -> list[DecisionItem]:
    return _registry.list_all(limit)

def list_for_mission(mission_id: str, limit: int = 100) -> list[DecisionItem]:
    return _registry.list_for_mission(mission_id, limit)

def list_active(mission_id: Optional[str] = None, limit: int = 100) -> list[DecisionItem]:
    return _registry.list_active(mission_id, limit)

def list_critical(limit: int = 50) -> list[DecisionItem]:
    return _registry.list_critical(limit)

def count() -> int:
    return _registry.count()

def stats() -> dict:
    return _registry.stats()

def _reset_for_testing() -> None:
    _registry._reset_for_testing()
