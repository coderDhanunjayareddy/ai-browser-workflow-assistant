"""
V9.0 Execution Planning Layer — PlanTimeline.

Per-mission + global event log for the plan lifecycle.
Events: created, validated, ready, cancelled, superseded, archived.

Same deque + RLock pattern as the V8.8 AuthorizationTimeline.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Any

MAX_PER_MISSION: int = 200
MAX_GLOBAL:      int = 1000

VALID_EVENTS: frozenset[str] = frozenset({
    "created", "validated", "ready", "cancelled", "superseded", "archived",
})


class PlanTimeline:

    def __init__(self) -> None:
        self._lock      = threading.RLock()
        self._timelines: dict[str, deque[dict]] = {}
        self._global:    deque[dict]            = deque(maxlen=MAX_GLOBAL)

    def record(
        self,
        plan_id:    str,
        event_type: str,
        mission_id: str = "",
        authorization_id: str = "",
        status:     str = "",
    ) -> None:
        entry: dict[str, Any] = {
            "plan_id":          plan_id,
            "event_type":       event_type,
            "mission_id":       mission_id,
            "authorization_id": authorization_id,
            "status":           status,
            "timestamp":        datetime.utcnow().isoformat(),
        }
        with self._lock:
            self._global.appendleft(entry)
            if mission_id:
                q = self._timelines.setdefault(mission_id, deque(maxlen=MAX_PER_MISSION))
                q.appendleft(entry)

    def get(self, mission_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            q = self._timelines.get(mission_id, deque())
            return list(q)[:limit]

    def recent_global(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._global)[:limit]

    def summary(self, mission_id: str) -> dict:
        with self._lock:
            q      = self._timelines.get(mission_id, deque())
            events = list(q)
        counts: dict[str, int] = {}
        for e in events:
            t = e.get("event_type", "unknown")
            counts[t] = counts.get(t, 0) + 1
        return {
            "mission_id":   mission_id,
            "event_count":  len(events),
            "type_counts":  counts,
            "latest_event": events[0] if events else None,
        }

    def missions_with_plans(self) -> list[str]:
        with self._lock:
            return [mid for mid, q in self._timelines.items() if q]

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._timelines.clear()
            self._global.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_timeline = PlanTimeline()


def record(plan_id: str, event_type: str, **kwargs) -> None:
    _timeline.record(plan_id, event_type, **kwargs)

def get(mission_id: str, limit: int = 50) -> list[dict]:
    return _timeline.get(mission_id, limit)

def recent_global(limit: int = 100) -> list[dict]:
    return _timeline.recent_global(limit)

def summary(mission_id: str) -> dict:
    return _timeline.summary(mission_id)

def missions_with_plans() -> list[str]:
    return _timeline.missions_with_plans()

def _reset_for_testing() -> None:
    _timeline._reset_for_testing()
