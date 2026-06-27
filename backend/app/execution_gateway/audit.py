"""
Phase B — Execution Gateway V1 — Audit Trail.

Append-only record of every dispatched action: timestamp, step, duration, result,
validation, retry count, rollback. Per-execution deque + global deque.

Same deque + RLock pattern as the V8.x timelines.
"""
from __future__ import annotations

import threading
from collections import deque

from app.execution_gateway.models import AuditEntry

MAX_PER_EXECUTION: int = 500
MAX_GLOBAL:        int = 5000


class AuditTrail:

    def __init__(self) -> None:
        self._lock   = threading.RLock()
        self._by_exec: dict[str, deque[AuditEntry]] = {}
        self._global:  deque[AuditEntry]            = deque(maxlen=MAX_GLOBAL)
        self._total: int = 0

    def append(self, entry: AuditEntry) -> None:
        with self._lock:
            q = self._by_exec.setdefault(entry.execution_id, deque(maxlen=MAX_PER_EXECUTION))
            q.append(entry)               # chronological (oldest first)
            self._global.append(entry)
            self._total += 1

    def entries_for_execution(self, execution_id: str, limit: int = 500) -> list[AuditEntry]:
        with self._lock:
            q = self._by_exec.get(execution_id, deque())
            return list(q)[:limit]

    def recent_global(self, limit: int = 100) -> list[AuditEntry]:
        with self._lock:
            return list(self._global)[-limit:][::-1]

    def count_for_execution(self, execution_id: str) -> int:
        with self._lock:
            return len(self._by_exec.get(execution_id, deque()))

    def total(self) -> int:
        with self._lock:
            return self._total

    def stats(self) -> dict:
        with self._lock:
            return {
                "total_entries":   self._total,
                "execution_keys":  len(self._by_exec),
                "global_buffered": len(self._global),
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._by_exec.clear()
            self._global.clear()
            self._total = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_audit = AuditTrail()


def append(entry: AuditEntry) -> None:                              _audit.append(entry)
def entries_for_execution(execution_id: str, limit: int = 500) -> list: return _audit.entries_for_execution(execution_id, limit)
def recent_global(limit: int = 100) -> list:                        return _audit.recent_global(limit)
def count_for_execution(execution_id: str) -> int:                  return _audit.count_for_execution(execution_id)
def total() -> int:                                                 return _audit.total()
def stats() -> dict:                                                return _audit.stats()
def _reset_for_testing() -> None:                                   _audit._reset_for_testing()
