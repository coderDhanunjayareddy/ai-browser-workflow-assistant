"""
Phase D — ExecutionTimeline (per-step).

Improves the audit with a queryable per-execution step timeline. Each step records the
lifecycle events: planned, started, retried, recovered, validated, completed, failed,
rollback.

Additive — does not touch the Phase B gateway timeline. Best-effort writes.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Any

MAX_PER_EXECUTION: int = 1000

VALID_EVENTS: frozenset[str] = frozenset({
    "planned", "started", "retried", "recovered", "validated",
    "completed", "failed", "rollback",
})


class ExecutionTimeline:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_exec: dict[str, deque[dict]] = {}

    def record(self, execution_id: str, step_id: str, event_type: str, *,
               order: int = 0, detail: dict | None = None) -> None:
        entry: dict[str, Any] = {
            "execution_id": execution_id,
            "step_id":      step_id,
            "order":        order,
            "event_type":   event_type,
            "detail":       detail or {},
            "timestamp":    datetime.utcnow().isoformat(),
        }
        with self._lock:
            q = self._by_exec.setdefault(execution_id, deque(maxlen=MAX_PER_EXECUTION))
            q.append(entry)   # chronological (oldest first)

    def events_for(self, execution_id: str, limit: int = 500) -> list[dict]:
        with self._lock:
            return list(self._by_exec.get(execution_id, deque()))[:limit]

    def events_for_step(self, execution_id: str, step_id: str) -> list[dict]:
        with self._lock:
            return [e for e in self._by_exec.get(execution_id, deque()) if e["step_id"] == step_id]

    def summary(self, execution_id: str) -> dict:
        with self._lock:
            events = list(self._by_exec.get(execution_id, deque()))
        counts: dict[str, int] = {}
        for e in events:
            t = e["event_type"]
            counts[t] = counts.get(t, 0) + 1
        return {
            "execution_id": execution_id,
            "event_count":  len(events),
            "type_counts":  counts,
            "events":       events,
        }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._by_exec.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_timeline = ExecutionTimeline()


def record(execution_id: str, step_id: str, event_type: str, **kwargs) -> None:
    _timeline.record(execution_id, step_id, event_type, **kwargs)

def events_for(execution_id: str, limit: int = 500) -> list[dict]:
    return _timeline.events_for(execution_id, limit)

def events_for_step(execution_id: str, step_id: str) -> list[dict]:
    return _timeline.events_for_step(execution_id, step_id)

def summary(execution_id: str) -> dict:
    return _timeline.summary(execution_id)

def _reset_for_testing() -> None:
    _timeline._reset_for_testing()
