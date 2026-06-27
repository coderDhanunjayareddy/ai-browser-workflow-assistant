"""
Phase B — Execution Gateway V1 — ExecutionRegistry.

In-memory TTL store of ExecutionRecords. Same RLock + monotonic pattern as the
other V8.x/V9.0 registries.

Indexes:
  execution_id → record
  mission_id   → set of execution_ids
  plan_id      → set of execution_ids
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.execution_gateway.models import ExecutionRecord, ExecutionState

EXECUTION_TTL: float = 604800.0    # 7 days


class ExecutionRegistry:

    def __init__(self, ttl: float = EXECUTION_TTL) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        self._records: dict[str, tuple[ExecutionRecord, float]] = {}
        self._by_mission: dict[str, set[str]] = {}
        self._by_plan:    dict[str, set[str]] = {}
        self._total_added:   int = 0
        self._total_evicted: int = 0

    def add(self, record: ExecutionRecord) -> None:
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            self._records[record.execution_id] = (record, now)
            if record.mission_id:
                self._by_mission.setdefault(record.mission_id, set()).add(record.execution_id)
            self._by_plan.setdefault(record.plan_id, set()).add(record.execution_id)
            self._total_added += 1

    def touch(self, execution_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            entry = self._records.get(execution_id)
            if entry is not None:
                self._records[execution_id] = (entry[0], now)

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        now = time.monotonic()
        with self._lock:
            entry = self._records.get(execution_id)
            if entry is None:
                return None
            record, inserted = entry
            if now - inserted > self._ttl:
                self._remove_locked(execution_id)
                self._total_evicted += 1
                return None
            return record

    def list_all(self, limit: int = 100) -> list[ExecutionRecord]:
        now = time.monotonic()
        with self._lock:
            valid = [(r, t) for (r, t) in self._records.values() if now - t <= self._ttl]
        valid.sort(key=lambda pair: pair[0].created_at, reverse=True)
        return [r for r, _ in valid[:limit]]

    def list_for_mission(self, mission_id: str, limit: int = 100) -> list[ExecutionRecord]:
        with self._lock:
            ids = list(self._by_mission.get(mission_id, set()))
        recs = [r for r in (self.get(i) for i in ids) if r is not None]
        recs.sort(key=lambda r: r.created_at, reverse=True)
        return recs[:limit]

    def list_for_plan(self, plan_id: str, limit: int = 100) -> list[ExecutionRecord]:
        with self._lock:
            ids = list(self._by_plan.get(plan_id, set()))
        recs = [r for r in (self.get(i) for i in ids) if r is not None]
        recs.sort(key=lambda r: r.created_at, reverse=True)
        return recs[:limit]

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for (_, t) in self._records.values() if now - t <= self._ttl)

    def count_by_state(self, state: ExecutionState) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for (r, t) in self._records.values()
                       if now - t <= self._ttl and r.state == state)

    def summary_for_mission(self, mission_id: str) -> dict:
        recs = self.list_for_mission(mission_id, limit=10000)
        running = [r for r in recs if r.state == ExecutionState.running]
        latest = recs[0] if recs else None
        return {
            "total_executions":     len(recs),
            "running_executions":   sum(1 for r in recs if r.state == ExecutionState.running),
            "completed_executions": sum(1 for r in recs if r.state == ExecutionState.completed),
            "failed_executions":    sum(1 for r in recs if r.state == ExecutionState.failed),
            "aborted_executions":   sum(1 for r in recs if r.state == ExecutionState.aborted),
            "latest_execution_id":  latest.execution_id if latest else None,
            "latest_state":         latest.state.value if latest else None,
            "execution_ids":        [r.execution_id for r in recs],
        }

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            valid = [(r, t) for (r, t) in self._records.values() if now - t <= self._ttl]
        return {
            "cached_executions": len(valid),
            "total_added":       self._total_added,
            "total_evicted":     self._total_evicted,
            "running_count":     sum(1 for r, _ in valid if r.state == ExecutionState.running),
            "mission_keys":      len(self._by_mission),
            "plan_keys":         len(self._by_plan),
        }

    def _evict_expired(self, now: float) -> None:
        expired = [eid for eid, (_, t) in self._records.items() if now - t > self._ttl]
        for eid in expired:
            self._remove_locked(eid)
            self._total_evicted += 1

    def _remove_locked(self, execution_id: str) -> None:
        entry = self._records.pop(execution_id, None)
        if not entry:
            return
        rec = entry[0]
        if rec.mission_id and rec.mission_id in self._by_mission:
            self._by_mission[rec.mission_id].discard(execution_id)
        if rec.plan_id in self._by_plan:
            self._by_plan[rec.plan_id].discard(execution_id)

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._records.clear()
            self._by_mission.clear()
            self._by_plan.clear()
            self._total_added   = 0
            self._total_evicted = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_registry = ExecutionRegistry()


def add(record: ExecutionRecord) -> None:                            _registry.add(record)
def touch(execution_id: str) -> None:                                _registry.touch(execution_id)
def get(execution_id: str) -> Optional[ExecutionRecord]:             return _registry.get(execution_id)
def list_all(limit: int = 100) -> list[ExecutionRecord]:             return _registry.list_all(limit)
def list_for_mission(mission_id: str, limit: int = 100) -> list:     return _registry.list_for_mission(mission_id, limit)
def list_for_plan(plan_id: str, limit: int = 100) -> list:           return _registry.list_for_plan(plan_id, limit)
def count() -> int:                                                  return _registry.count()
def count_by_state(state: ExecutionState) -> int:                    return _registry.count_by_state(state)
def summary_for_mission(mission_id: str) -> dict:                    return _registry.summary_for_mission(mission_id)
def stats() -> dict:                                                 return _registry.stats()
def _reset_for_testing() -> None:                                    _registry._reset_for_testing()
