"""
V8.0 Human Approval Center — ApprovalRegistry.

In-memory store for ApprovalRequest objects.
TTL = 86400s (24 h) — matches default approval expiry.
RLock + monotonic pattern reused from V6.5/V7.0/V7.5.

Auto-expiry: PENDING items past expires_at are transitioned to EXPIRED on first access.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Optional

from app.approvals.models import (
    ApprovalRequest, ApprovalStatus, ApprovalRiskLevel, RISK_ORDER,
)

TTL_SECONDS: int = 86400   # 24 h registry TTL (separate from approval expiry)


class ApprovalRegistry:

    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        # approval_id → (ApprovalRequest, inserted_at_monotonic)
        self._items:      dict[str, tuple[ApprovalRequest, float]] = {}
        # mission_id → set[approval_id]
        self._by_mission: dict[str, set[str]] = defaultdict(set)
        # task_id → set[approval_id]
        self._by_task:    dict[str, set[str]] = defaultdict(set)
        self._total_added:   int = 0
        self._total_evicted: int = 0

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _is_ttl_expired(self, inserted_at: float, now: float) -> bool:
        return now - inserted_at > self._ttl

    def _check_approval_expiry(self, item: ApprovalRequest) -> None:
        """Transition PENDING items past expires_at → EXPIRED (in-place)."""
        if item.status == ApprovalStatus.pending and time.time() > item.expires_at:
            item.status = ApprovalStatus.expired
            item.resolved_at = time.time()

    def _evict(self, approval_id: str, item: ApprovalRequest) -> None:
        self._items.pop(approval_id, None)
        if item.mission_id:
            self._by_mission[item.mission_id].discard(approval_id)
        if item.task_id:
            self._by_task[item.task_id].discard(approval_id)
        self._total_evicted += 1

    # ── Public API ───────────────────────────────────────────────────────────

    def add(self, item: ApprovalRequest) -> None:
        now = time.monotonic()
        with self._lock:
            self._items[item.approval_id] = (item, now)
            if item.mission_id:
                self._by_mission[item.mission_id].add(item.approval_id)
            if item.task_id:
                self._by_task[item.task_id].add(item.approval_id)
            self._total_added += 1

    def get(self, approval_id: str) -> Optional[ApprovalRequest]:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(approval_id)
            if entry is None:
                return None
            item, inserted_at = entry
            if self._is_ttl_expired(inserted_at, now):
                self._evict(approval_id, item)
                return None
            self._check_approval_expiry(item)
            return item

    def approve(self, approval_id: str, decision_source: str = "human_via_api") -> bool:
        with self._lock:
            entry = self._items.get(approval_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != ApprovalStatus.pending:
                return False
            item.status      = ApprovalStatus.approved
            item.resolved_at = time.time()
            item.resolved_by = decision_source
            return True

    def reject(self, approval_id: str, reason: str = "",
               decision_source: str = "human_via_api") -> bool:
        with self._lock:
            entry = self._items.get(approval_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != ApprovalStatus.pending:
                return False
            item.status           = ApprovalStatus.rejected
            item.resolved_at      = time.time()
            item.resolved_by      = decision_source
            item.rejection_reason = reason
            return True

    def expire(self, approval_id: str) -> bool:
        with self._lock:
            entry = self._items.get(approval_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != ApprovalStatus.pending:
                return False
            item.status      = ApprovalStatus.expired
            item.resolved_at = time.time()
            return True

    def cancel(self, approval_id: str) -> bool:
        with self._lock:
            entry = self._items.get(approval_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status not in (ApprovalStatus.pending,):
                return False
            item.status      = ApprovalStatus.cancelled
            item.resolved_at = time.time()
            return True

    def list_all(self, limit: int = 100) -> list[ApprovalRequest]:
        now = time.monotonic()
        with self._lock:
            valid = []
            for item, inserted_at in self._items.values():
                if self._is_ttl_expired(inserted_at, now):
                    continue
                self._check_approval_expiry(item)
                valid.append(item)
        valid.sort(key=lambda r: (-r.risk_order, -r.created_at))
        return valid[:limit]

    def list_pending(self, limit: int = 100) -> list[ApprovalRequest]:
        items = [r for r in self.list_all(limit=1000) if r.status == ApprovalStatus.pending]
        return items[:limit]

    def list_for_mission(self, mission_id: str, limit: int = 100) -> list[ApprovalRequest]:
        now = time.monotonic()
        with self._lock:
            ids = self._by_mission.get(mission_id, set()).copy()
            out = []
            for aid in ids:
                entry = self._items.get(aid)
                if entry is None:
                    continue
                item, inserted_at = entry
                if self._is_ttl_expired(inserted_at, now):
                    self._evict(aid, item)
                    continue
                self._check_approval_expiry(item)
                out.append(item)
        out.sort(key=lambda r: (-r.risk_order, -r.created_at))
        return out[:limit]

    def list_for_task(self, task_id: str, limit: int = 100) -> list[ApprovalRequest]:
        now = time.monotonic()
        with self._lock:
            ids = self._by_task.get(task_id, set()).copy()
            out = []
            for aid in ids:
                entry = self._items.get(aid)
                if entry is None:
                    continue
                item, inserted_at = entry
                if self._is_ttl_expired(inserted_at, now):
                    self._evict(aid, item)
                    continue
                self._check_approval_expiry(item)
                out.append(item)
        out.sort(key=lambda r: (-r.risk_order, -r.created_at))
        return out[:limit]

    def list_critical(self, limit: int = 50) -> list[ApprovalRequest]:
        return [r for r in self.list_pending(limit=1000)
                if r.risk_level in (ApprovalRiskLevel.critical, ApprovalRiskLevel.high)][:limit]

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(
                1 for _, inserted_at in self._items.values()
                if not self._is_ttl_expired(inserted_at, now)
            )

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            valid = [(item, ins) for item, ins in self._items.values()
                     if not self._is_ttl_expired(ins, now)]
        return {
            "cached_items":   len(valid),
            "total_added":    self._total_added,
            "total_evicted":  self._total_evicted,
            "pending_count":  sum(1 for i, _ in valid if i.status == ApprovalStatus.pending),
            "approved_count": sum(1 for i, _ in valid if i.status == ApprovalStatus.approved),
            "rejected_count": sum(1 for i, _ in valid if i.status == ApprovalStatus.rejected),
        }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._items.clear()
            self._by_mission.clear()
            self._by_task.clear()
            self._total_added   = 0
            self._total_evicted = 0


# Module-level singleton
_registry = ApprovalRegistry()


def add(item: ApprovalRequest) -> None:
    _registry.add(item)

def get(approval_id: str) -> Optional[ApprovalRequest]:
    return _registry.get(approval_id)

def approve(approval_id: str, decision_source: str = "human_via_api") -> bool:
    return _registry.approve(approval_id, decision_source)

def reject(approval_id: str, reason: str = "",
           decision_source: str = "human_via_api") -> bool:
    return _registry.reject(approval_id, reason, decision_source)

def expire(approval_id: str) -> bool:
    return _registry.expire(approval_id)

def cancel(approval_id: str) -> bool:
    return _registry.cancel(approval_id)

def list_all(limit: int = 100) -> list[ApprovalRequest]:
    return _registry.list_all(limit)

def list_pending(limit: int = 100) -> list[ApprovalRequest]:
    return _registry.list_pending(limit)

def list_for_mission(mission_id: str, limit: int = 100) -> list[ApprovalRequest]:
    return _registry.list_for_mission(mission_id, limit)

def list_for_task(task_id: str, limit: int = 100) -> list[ApprovalRequest]:
    return _registry.list_for_task(task_id, limit)

def list_critical(limit: int = 50) -> list[ApprovalRequest]:
    return _registry.list_critical(limit)

def count() -> int:
    return _registry.count()

def stats() -> dict:
    return _registry.stats()

def _reset_for_testing() -> None:
    _registry._reset_for_testing()
