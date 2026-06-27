"""
V9.0 Execution Planning Layer — PlanRegistry.

In-memory store of ExecutionPlans with TTL eviction.
Same RLock + monotonic pattern as the V8.8 AuthorizationRegistry.

Indexes:
  plan_id          → plan
  authorization_id → latest plan_id  (+ full history deque)
  mission_id       → set of plan_ids
  task_id          → set of plan_ids

NO execution. NO persistence (in-memory only; V9.0 persistence flag is a stub).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

from app.execution_planning.models import ExecutionPlan, PlanStatus

PLAN_TTL: float = 604800.0    # 7 days (mirrors authorization TTL)
HISTORY_PER_AUTH: int = 50


class PlanRegistry:

    def __init__(self, ttl: float = PLAN_TTL) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        # plan_id → (plan, inserted_monotonic)
        self._plans: dict[str, tuple[ExecutionPlan, float]] = {}
        self._by_auth:    dict[str, str]            = {}   # auth_id → latest plan_id
        self._by_mission: dict[str, set[str]]       = {}
        self._by_task:    dict[str, set[str]]        = {}
        self._history:    dict[str, deque[str]]      = {}   # auth_id → plan_ids
        self._total_added:   int = 0
        self._total_evicted: int = 0

    # ── Write ────────────────────────────────────────────────────────────────

    def add(self, plan: ExecutionPlan) -> None:
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            self._plans[plan.plan_id] = (plan, now)
            self._by_auth[plan.authorization_id] = plan.plan_id
            h = self._history.setdefault(plan.authorization_id, deque(maxlen=HISTORY_PER_AUTH))
            h.appendleft(plan.plan_id)
            if plan.mission_id:
                self._by_mission.setdefault(plan.mission_id, set()).add(plan.plan_id)
            if plan.task_id:
                self._by_task.setdefault(plan.task_id, set()).add(plan.plan_id)
            self._total_added += 1

    def set_status(self, plan_id: str, status: PlanStatus) -> bool:
        with self._lock:
            entry = self._plans.get(plan_id)
            if entry is None:
                return False
            entry[0].status = status
            return True

    def mark_validated(self, plan_id: str, validated_at: float) -> bool:
        with self._lock:
            entry = self._plans.get(plan_id)
            if entry is None:
                return False
            entry[0].validated_at = validated_at
            return True

    def archive(self, plan_id: str, archived_at: float) -> bool:
        with self._lock:
            entry = self._plans.get(plan_id)
            if entry is None:
                return False
            plan = entry[0]
            if plan.status == PlanStatus.aborted:
                return False
            plan.status = PlanStatus.aborted
            plan.archived_at = archived_at
            return True

    def supersede(self, old_plan_id: str, new_plan_id: str) -> bool:
        with self._lock:
            entry = self._plans.get(old_plan_id)
            if entry is None:
                return False
            entry[0].superseded_by = new_plan_id
            entry[0].status = PlanStatus.aborted
            return True

    # ── Read ─────────────────────────────────────────────────────────────────

    def get(self, plan_id: str) -> Optional[ExecutionPlan]:
        now = time.monotonic()
        with self._lock:
            entry = self._plans.get(plan_id)
            if entry is None:
                return None
            plan, inserted = entry
            if now - inserted > self._ttl:
                self._remove_locked(plan_id)
                self._total_evicted += 1
                return None
            return plan

    def get_for_authorization(self, authorization_id: str) -> Optional[ExecutionPlan]:
        with self._lock:
            pid = self._by_auth.get(authorization_id)
        return self.get(pid) if pid else None

    def history_for_authorization(self, authorization_id: str, limit: int = 20) -> list[ExecutionPlan]:
        with self._lock:
            ids = list(self._history.get(authorization_id, deque()))[:limit]
        return [p for p in (self.get(i) for i in ids) if p is not None]

    def list_all(self, limit: int = 100) -> list[ExecutionPlan]:
        now = time.monotonic()
        with self._lock:
            valid = [(p, t) for (p, t) in self._plans.values() if now - t <= self._ttl]
        valid.sort(key=lambda pair: pair[0].created_at, reverse=True)
        return [p for p, _ in valid[:limit]]

    def list_for_mission(self, mission_id: str, limit: int = 100) -> list[ExecutionPlan]:
        with self._lock:
            ids = list(self._by_mission.get(mission_id, set()))
        plans = [p for p in (self.get(i) for i in ids) if p is not None]
        plans.sort(key=lambda p: p.created_at, reverse=True)
        return plans[:limit]

    def list_for_task(self, task_id: str, limit: int = 100) -> list[ExecutionPlan]:
        with self._lock:
            ids = list(self._by_task.get(task_id, set()))
        plans = [p for p in (self.get(i) for i in ids) if p is not None]
        plans.sort(key=lambda p: p.created_at, reverse=True)
        return plans[:limit]

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for (_, t) in self._plans.values() if now - t <= self._ttl)

    def count_by_status(self, status: PlanStatus) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for (p, t) in self._plans.values()
                       if now - t <= self._ttl and p.status == status)

    def summary_for_mission(self, mission_id: str) -> dict:
        plans = self.list_for_mission(mission_id, limit=10000)
        ready = [p for p in plans if p.status == PlanStatus.ready]
        active = ready[0] if ready else (plans[0] if plans else None)
        return {
            "total_plans":      len(plans),
            "ready_plans":      len(ready),
            "draft_plans":      sum(1 for p in plans if p.status == PlanStatus.draft),
            "archived_plans":   sum(1 for p in plans if p.status == PlanStatus.aborted),
            "active_plan_id":   active.plan_id if active else None,
            "plan_ids":         [p.plan_id for p in plans],
        }

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            valid = [(p, t) for (p, t) in self._plans.values() if now - t <= self._ttl]
        return {
            "cached_plans":  len(valid),
            "total_added":   self._total_added,
            "total_evicted": self._total_evicted,
            "ready_count":   sum(1 for p, _ in valid if p.status == PlanStatus.ready),
            "mission_keys":  len(self._by_mission),
            "task_keys":     len(self._by_task),
        }

    # ── Housekeeping ─────────────────────────────────────────────────────────

    def _evict_expired(self, now: float) -> None:
        expired = [pid for pid, (_, t) in self._plans.items() if now - t > self._ttl]
        for pid in expired:
            self._remove_locked(pid)
            self._total_evicted += 1

    def _remove_locked(self, plan_id: str) -> None:
        entry = self._plans.pop(plan_id, None)
        if not entry:
            return
        plan = entry[0]
        if plan.mission_id and plan.mission_id in self._by_mission:
            self._by_mission[plan.mission_id].discard(plan_id)
        if plan.task_id and plan.task_id in self._by_task:
            self._by_task[plan.task_id].discard(plan_id)
        if self._by_auth.get(plan.authorization_id) == plan_id:
            self._by_auth.pop(plan.authorization_id, None)

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._plans.clear()
            self._by_auth.clear()
            self._by_mission.clear()
            self._by_task.clear()
            self._history.clear()
            self._total_added   = 0
            self._total_evicted = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_registry = PlanRegistry()


def add(plan: ExecutionPlan) -> None:                                  _registry.add(plan)
def set_status(plan_id: str, status: PlanStatus) -> bool:             return _registry.set_status(plan_id, status)
def mark_validated(plan_id: str, validated_at: float) -> bool:        return _registry.mark_validated(plan_id, validated_at)
def archive(plan_id: str, archived_at: float) -> bool:                return _registry.archive(plan_id, archived_at)
def supersede(old_plan_id: str, new_plan_id: str) -> bool:            return _registry.supersede(old_plan_id, new_plan_id)
def get(plan_id: str) -> Optional[ExecutionPlan]:                     return _registry.get(plan_id)
def get_for_authorization(authorization_id: str) -> Optional[ExecutionPlan]: return _registry.get_for_authorization(authorization_id)
def history_for_authorization(authorization_id: str, limit: int = 20) -> list: return _registry.history_for_authorization(authorization_id, limit)
def list_all(limit: int = 100) -> list[ExecutionPlan]:               return _registry.list_all(limit)
def list_for_mission(mission_id: str, limit: int = 100) -> list:     return _registry.list_for_mission(mission_id, limit)
def list_for_task(task_id: str, limit: int = 100) -> list:           return _registry.list_for_task(task_id, limit)
def count() -> int:                                                  return _registry.count()
def count_by_status(status: PlanStatus) -> int:                      return _registry.count_by_status(status)
def summary_for_mission(mission_id: str) -> dict:                    return _registry.summary_for_mission(mission_id)
def stats() -> dict:                                                 return _registry.stats()
def _reset_for_testing() -> None:                                    _registry._reset_for_testing()
