"""
V7.0 Live Browser Sync Layer — BrowserActivityTimeline.

Chronological, per-mission event stream.
Append-only deque (max 200 entries per mission).
Reuses the timeline-deque concept from the unified task timeline.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any

from app.browser.models import BrowserEvent, BrowserEventType

MAX_PER_MISSION: int = 200
MAX_GLOBAL:      int = 500


class BrowserActivityTimeline:

    def __init__(self) -> None:
        self._lock     = threading.RLock()
        # mission_id → deque[dict] newest-first
        self._timelines: dict[str, deque[dict]] = {}
        # global recent stream (newest-first)
        self._global:    deque[dict]             = deque(maxlen=MAX_GLOBAL)

    def append(self, mission_id: str, event: BrowserEvent) -> None:
        entry = event.to_dict()
        with self._lock:
            q = self._timelines.setdefault(mission_id, deque(maxlen=MAX_PER_MISSION))
            q.appendleft(entry)
            self._global.appendleft(entry)

    def append_global(self, event: BrowserEvent) -> None:
        """Append event to global stream only (no mission context)."""
        entry = event.to_dict()
        with self._lock:
            self._global.appendleft(entry)

    def get(self, mission_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            q = self._timelines.get(mission_id, deque())
            return list(q)[:limit]

    def recent_global(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._global)[:limit]

    def summary(self, mission_id: str) -> dict[str, Any]:
        with self._lock:
            q = self._timelines.get(mission_id, deque())
            events = list(q)
        counts: dict[str, int] = {}
        for e in events:
            t = e.get("event_type", "UNKNOWN")
            counts[t] = counts.get(t, 0) + 1
        return {
            "mission_id":   mission_id,
            "event_count":  len(events),
            "type_counts":  counts,
            "latest_event": events[0] if events else None,
        }

    def missions_with_activity(self) -> list[str]:
        with self._lock:
            return [mid for mid, q in self._timelines.items() if q]

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._timelines.clear()
            self._global.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_timeline = BrowserActivityTimeline()


def append(mission_id: str, event: BrowserEvent) -> None:
    _timeline.append(mission_id, event)

def append_global(event: BrowserEvent) -> None:
    _timeline.append_global(event)

def get(mission_id: str, limit: int = 50) -> list[dict]:
    return _timeline.get(mission_id, limit)

def recent_global(limit: int = 100) -> list[dict]:
    return _timeline.recent_global(limit)

def summary(mission_id: str) -> dict:
    return _timeline.summary(mission_id)

def missions_with_activity() -> list[str]:
    return _timeline.missions_with_activity()

def _reset_for_testing() -> None:
    _timeline._reset_for_testing()
