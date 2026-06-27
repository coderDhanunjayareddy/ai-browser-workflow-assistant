"""
V8.9 Browser Runtime Layer — RuntimeEventQueue.

Bounded, newest-first queue of RuntimeEvents.
Global queue cap: QUEUE_LIMIT = 500 (oldest evicted on overflow).
Per-runtime index for fast retrieval.

Reuses the deque + RLock timeline pattern from V8.8 AuthorizationTimeline.
NO AI. NO autonomy.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any

from app.runtime.models import RuntimeEvent

QUEUE_LIMIT:     int = 500
MAX_PER_RUNTIME: int = 200


class RuntimeEventQueue:

    def __init__(self, limit: int = QUEUE_LIMIT) -> None:
        self._lock   = threading.RLock()
        self._global: deque[RuntimeEvent]            = deque(maxlen=limit)
        self._by_runtime: dict[str, deque[RuntimeEvent]] = {}
        self._total_enqueued: int = 0

    def enqueue(self, event: RuntimeEvent) -> None:
        with self._lock:
            self._global.appendleft(event)
            q = self._by_runtime.setdefault(event.runtime_id, deque(maxlen=MAX_PER_RUNTIME))
            q.appendleft(event)
            self._total_enqueued += 1

    def enqueue_many(self, events: list[RuntimeEvent]) -> int:
        n = 0
        for e in events:
            self.enqueue(e)
            n += 1
        return n

    def get_for_runtime(self, runtime_id: str, limit: int = 50) -> list[RuntimeEvent]:
        with self._lock:
            q = self._by_runtime.get(runtime_id, deque())
            return list(q)[:limit]

    def recent_global(self, limit: int = 100) -> list[RuntimeEvent]:
        with self._lock:
            return list(self._global)[:limit]

    def count(self) -> int:
        with self._lock:
            return len(self._global)

    def count_for_runtime(self, runtime_id: str) -> int:
        with self._lock:
            return len(self._by_runtime.get(runtime_id, deque()))

    def summary(self, runtime_id: str) -> dict[str, Any]:
        with self._lock:
            q      = self._by_runtime.get(runtime_id, deque())
            events = list(q)
        counts: dict[str, int] = {}
        for e in events:
            t = e.event_type.value
            counts[t] = counts.get(t, 0) + 1
        return {
            "runtime_id":   runtime_id,
            "event_count":  len(events),
            "type_counts":  counts,
            "latest_event": events[0].to_dict() if events else None,
        }

    def runtimes_with_events(self) -> list[str]:
        with self._lock:
            return [rid for rid, q in self._by_runtime.items() if q]

    def stats(self) -> dict:
        with self._lock:
            return {
                "queued_global":   len(self._global),
                "total_enqueued":  self._total_enqueued,
                "runtime_keys":    len(self._by_runtime),
                "queue_limit":     self._global.maxlen,
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._global.clear()
            self._by_runtime.clear()
            self._total_enqueued = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_queue = RuntimeEventQueue()


def enqueue(event: RuntimeEvent) -> None:                            _queue.enqueue(event)
def enqueue_many(events: list[RuntimeEvent]) -> int:                 return _queue.enqueue_many(events)
def get_for_runtime(runtime_id: str, limit: int = 50) -> list:       return _queue.get_for_runtime(runtime_id, limit)
def recent_global(limit: int = 100) -> list:                         return _queue.recent_global(limit)
def count() -> int:                                                  return _queue.count()
def count_for_runtime(runtime_id: str) -> int:                       return _queue.count_for_runtime(runtime_id)
def summary(runtime_id: str) -> dict:                                return _queue.summary(runtime_id)
def runtimes_with_events() -> list[str]:                             return _queue.runtimes_with_events()
def stats() -> dict:                                                 return _queue.stats()
def _reset_for_testing() -> None:                                    _queue._reset_for_testing()
