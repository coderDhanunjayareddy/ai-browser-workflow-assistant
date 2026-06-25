"""
V7.0 Live Browser Sync Layer — BrowserEventRegistry.

In-memory TTL cache for BrowserEvents.
Same RLock + monotonic pattern as TrustRegistry and MissionIntelligenceRegistry.

TTL:  300 seconds (events stay fresh for 5 minutes)
Max:  1 000 events total (oldest evicted on overflow)

Indexed by:
  event_id  → fast single-event lookup
  mission_id → list of recent event_ids (newest first, max 100 per mission)
  tab_id     → list of recent event_ids (newest first, max 100 per tab)
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

from app.browser.models import BrowserEvent

TTL_SECONDS: int = 300
MAX_EVENTS:  int = 1_000
MAX_PER_KEY: int = 100


class BrowserEventRegistry:

    def __init__(self, ttl: int = TTL_SECONDS, max_events: int = MAX_EVENTS) -> None:
        self._ttl        = ttl
        self._max        = max_events
        self._lock       = threading.RLock()
        # event_id → (event, inserted_at)
        self._cache:    dict[str, tuple[BrowserEvent, float]] = {}
        # mission_id → deque of event_ids, newest-first
        self._by_mission: dict[str, deque[str]] = {}
        # tab_id → deque of event_ids, newest-first
        self._by_tab:     dict[str, deque[str]] = {}
        # insertion-order list for FIFO eviction
        self._order: deque[tuple[str, float]] = deque()   # (event_id, inserted_at)
        # counters
        self._total_registered: int = 0
        self._total_evicted:    int = 0

    # ── Write ──────────────────────────────────────────────────────────────────

    def register(self, event: BrowserEvent) -> None:
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            self._enforce_cap()
            self._cache[event.event_id] = (event, now)
            self._order.append((event.event_id, now))
            if event.mission_id:
                q = self._by_mission.setdefault(event.mission_id, deque())
                q.appendleft(event.event_id)
                if len(q) > MAX_PER_KEY:
                    q.pop()
            q_tab = self._by_tab.setdefault(event.tab_id, deque())
            q_tab.appendleft(event.event_id)
            if len(q_tab) > MAX_PER_KEY:
                q_tab.pop()
            self._total_registered += 1

    # ── Read ───────────────────────────────────────────────────────────────────

    def get(self, event_id: str) -> Optional[BrowserEvent]:
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(event_id)
            if entry is None:
                return None
            ev, inserted_at = entry
            if now - inserted_at > self._ttl:
                del self._cache[event_id]
                return None
            return ev

    def events_for_mission(self, mission_id: str, limit: int = 20) -> list[BrowserEvent]:
        now = time.monotonic()
        with self._lock:
            ids = list(self._by_mission.get(mission_id, []))
        result: list[BrowserEvent] = []
        for eid in ids:
            if len(result) >= limit:
                break
            with self._lock:
                entry = self._cache.get(eid)
            if entry and (now - entry[1]) <= self._ttl:
                result.append(entry[0])
        return result

    def events_for_tab(self, tab_id: str, limit: int = 20) -> list[BrowserEvent]:
        now = time.monotonic()
        with self._lock:
            ids = list(self._by_tab.get(tab_id, []))
        result: list[BrowserEvent] = []
        for eid in ids:
            if len(result) >= limit:
                break
            with self._lock:
                entry = self._cache.get(eid)
            if entry and (now - entry[1]) <= self._ttl:
                result.append(entry[0])
        return result

    def recent_events(self, limit: int = 50) -> list[BrowserEvent]:
        now = time.monotonic()
        result: list[BrowserEvent] = []
        with self._lock:
            # _order is oldest-first; iterate in reverse
            order_snapshot = list(self._order)
        for event_id, inserted_at in reversed(order_snapshot):
            if len(result) >= limit:
                break
            if now - inserted_at > self._ttl:
                continue
            with self._lock:
                entry = self._cache.get(event_id)
            if entry:
                result.append(entry[0])
        return result

    def count(self) -> int:
        with self._lock:
            return len(self._cache)

    # ── Housekeeping ───────────────────────────────────────────────────────────

    def _evict_expired(self, now: float) -> int:
        evicted = 0
        while self._order:
            event_id, inserted_at = self._order[0]
            if now - inserted_at > self._ttl:
                self._order.popleft()
                self._cache.pop(event_id, None)
                evicted += 1
            else:
                break
        self._total_evicted += evicted
        return evicted

    def _enforce_cap(self) -> None:
        while len(self._cache) >= self._max and self._order:
            event_id, _ = self._order.popleft()
            self._cache.pop(event_id, None)
            self._total_evicted += 1

    def stats(self) -> dict:
        with self._lock:
            return {
                "cached_events":    len(self._cache),
                "total_registered": self._total_registered,
                "total_evicted":    self._total_evicted,
                "ttl_seconds":      self._ttl,
                "max_events":       self._max,
                "mission_keys":     len(self._by_mission),
                "tab_keys":         len(self._by_tab),
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._cache.clear()
            self._by_mission.clear()
            self._by_tab.clear()
            self._order.clear()
            self._total_registered = 0
            self._total_evicted    = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_registry = BrowserEventRegistry()


def register(event: BrowserEvent) -> None:
    _registry.register(event)

def get(event_id: str) -> Optional[BrowserEvent]:
    return _registry.get(event_id)

def events_for_mission(mission_id: str, limit: int = 20) -> list[BrowserEvent]:
    return _registry.events_for_mission(mission_id, limit)

def events_for_tab(tab_id: str, limit: int = 20) -> list[BrowserEvent]:
    return _registry.events_for_tab(tab_id, limit)

def recent_events(limit: int = 50) -> list[BrowserEvent]:
    return _registry.recent_events(limit)

def count() -> int:
    return _registry.count()

def stats() -> dict:
    return _registry.stats()

def _reset_for_testing() -> None:
    _registry._reset_for_testing()
