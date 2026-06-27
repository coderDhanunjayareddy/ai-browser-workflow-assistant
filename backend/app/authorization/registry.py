"""
V8.8 Execution Authorization Framework — AuthorizationRegistry.

Stores ExecutionAuthorization objects.
Follows the TTL + RLock + auto-expiry pattern from V6.5/V7.0/V7.5/V8.0/V8.5.

Indexes:
  - authorization_id → (ExecutionAuthorization, inserted_at_mono)
  - contract_id  → latest authorization_id (one-to-one, overwritten on re-evaluation)
  - mission_id   → set[authorization_id]
  - task_id      → set[authorization_id]

History: per contract list (newest-first) of all authorization_ids ever stored.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Optional

from app.authorization.models import ExecutionAuthorization, AuthorizationStatus

TTL_SECONDS: int = 604800   # 7 days


class AuthorizationRegistry:

    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        self._items:     dict[str, tuple[ExecutionAuthorization, float]] = {}
        self._by_contract: dict[str, str] = {}               # contract_id → latest auth_id
        self._by_mission:  dict[str, set[str]] = defaultdict(set)
        self._by_task:     dict[str, set[str]] = defaultdict(set)
        self._history:     dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=50))
        self._total_added:   int = 0
        self._total_evicted: int = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _is_ttl_expired(self, inserted_at: float, now: float) -> bool:
        return now - inserted_at > self._ttl

    def _check_expiry(self, item: ExecutionAuthorization) -> None:
        if item.status in (AuthorizationStatus.active, AuthorizationStatus.denied):
            if time.time() > item.expires_at:
                item.status = AuthorizationStatus.expired

    def _evict(self, auth_id: str, item: ExecutionAuthorization) -> None:
        self._items.pop(auth_id, None)
        if item.mission_id:
            self._by_mission[item.mission_id].discard(auth_id)
        if item.task_id:
            self._by_task[item.task_id].discard(auth_id)
        self._total_evicted += 1

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, item: ExecutionAuthorization) -> None:
        now = time.monotonic()
        with self._lock:
            self._items[item.authorization_id] = (item, now)
            self._by_contract[item.contract_id] = item.authorization_id
            self._history[item.contract_id].appendleft(item.authorization_id)
            if item.mission_id:
                self._by_mission[item.mission_id].add(item.authorization_id)
            if item.task_id:
                self._by_task[item.task_id].add(item.authorization_id)
            self._total_added += 1

    def get(self, authorization_id: str) -> Optional[ExecutionAuthorization]:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(authorization_id)
            if entry is None:
                return None
            item, inserted_at = entry
            if self._is_ttl_expired(inserted_at, now):
                self._evict(authorization_id, item)
                return None
            self._check_expiry(item)
            return item

    def get_for_contract(self, contract_id: str) -> Optional[ExecutionAuthorization]:
        with self._lock:
            auth_id = self._by_contract.get(contract_id)
        if auth_id is None:
            return None
        return self.get(auth_id)

    def history_for_contract(self, contract_id: str, limit: int = 20) -> list[ExecutionAuthorization]:
        with self._lock:
            ids = list(self._history.get(contract_id, []))[:limit]
        out = []
        for aid in ids:
            item = self.get(aid)
            if item:
                out.append(item)
        return out

    def revoke(self, authorization_id: str, reason: str = "") -> bool:
        with self._lock:
            entry = self._items.get(authorization_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != AuthorizationStatus.active:
                return False
            item.status         = AuthorizationStatus.revoked
            item.revoked_at     = time.time()
            item.revoked_reason = reason
            return True

    def expire(self, authorization_id: str) -> bool:
        with self._lock:
            entry = self._items.get(authorization_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status not in (AuthorizationStatus.active, AuthorizationStatus.denied):
                return False
            item.status = AuthorizationStatus.expired
            return True

    def consume(self, authorization_id: str) -> bool:
        with self._lock:
            entry = self._items.get(authorization_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != AuthorizationStatus.active:
                return False
            item.status      = AuthorizationStatus.consumed
            item.consumed_at = time.time()
            return True

    def list_all(self, limit: int = 100) -> list[ExecutionAuthorization]:
        now = time.monotonic()
        with self._lock:
            valid = []
            for item, ins in self._items.values():
                if self._is_ttl_expired(ins, now):
                    continue
                self._check_expiry(item)
                valid.append(item)
        valid.sort(key=lambda a: -a.evaluated_at)
        return valid[:limit]

    def list_for_mission(self, mission_id: str, limit: int = 100) -> list[ExecutionAuthorization]:
        now = time.monotonic()
        with self._lock:
            ids = self._by_mission.get(mission_id, set()).copy()
            out = []
            for aid in ids:
                entry = self._items.get(aid)
                if entry is None:
                    continue
                item, ins = entry
                if self._is_ttl_expired(ins, now):
                    self._evict(aid, item)
                    continue
                self._check_expiry(item)
                out.append(item)
        out.sort(key=lambda a: -a.evaluated_at)
        return out[:limit]

    def list_for_task(self, task_id: str, limit: int = 100) -> list[ExecutionAuthorization]:
        now = time.monotonic()
        with self._lock:
            ids = self._by_task.get(task_id, set()).copy()
            out = []
            for aid in ids:
                entry = self._items.get(aid)
                if entry is None:
                    continue
                item, ins = entry
                if self._is_ttl_expired(ins, now):
                    continue
                self._check_expiry(item)
                out.append(item)
        out.sort(key=lambda a: -a.evaluated_at)
        return out[:limit]

    def list_executable(self, limit: int = 100) -> list[ExecutionAuthorization]:
        return [a for a in self.list_all(limit=10000) if a.is_executable][:limit]

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(
                1 for _, ins in self._items.values()
                if not self._is_ttl_expired(ins, now)
            )

    def count_by_status(self, status: AuthorizationStatus) -> int:
        return sum(1 for a in self.list_all(limit=10000) if a.status == status)

    def summary_for_mission(self, mission_id: str) -> dict:
        items = self.list_for_mission(mission_id, limit=10000)
        return {
            "total":                   len(items),
            "active_authorizations":   sum(1 for a in items if a.status == AuthorizationStatus.active),
            "denied_authorizations":   sum(1 for a in items if a.status == AuthorizationStatus.denied),
            "expired_authorizations":  sum(1 for a in items if a.status == AuthorizationStatus.expired),
            "revoked_authorizations":  sum(1 for a in items if a.status == AuthorizationStatus.revoked),
            "consumed_authorizations": sum(1 for a in items if a.status == AuthorizationStatus.consumed),
            "executable_tasks":        list({a.task_id for a in items if a.task_id and a.is_executable}),
        }

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            valid = [(item, ins) for item, ins in self._items.values()
                     if not self._is_ttl_expired(ins, now)]
        return {
            "cached_items":   len(valid),
            "total_added":    self._total_added,
            "total_evicted":  self._total_evicted,
            "active_count":   sum(1 for i, _ in valid if i.status == AuthorizationStatus.active),
        }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._items.clear()
            self._by_contract.clear()
            self._by_mission.clear()
            self._by_task.clear()
            self._history.clear()
            self._total_added   = 0
            self._total_evicted = 0


# Module-level singleton
_registry = AuthorizationRegistry()


def add(item: ExecutionAuthorization) -> None:                           _registry.add(item)
def get(authorization_id: str) -> Optional[ExecutionAuthorization]:      return _registry.get(authorization_id)
def get_for_contract(contract_id: str) -> Optional[ExecutionAuthorization]: return _registry.get_for_contract(contract_id)
def history_for_contract(contract_id: str, limit: int = 20) -> list:    return _registry.history_for_contract(contract_id, limit)
def revoke(authorization_id: str, reason: str = "") -> bool:             return _registry.revoke(authorization_id, reason)
def expire(authorization_id: str) -> bool:                               return _registry.expire(authorization_id)
def consume(authorization_id: str) -> bool:                              return _registry.consume(authorization_id)
def list_all(limit: int = 100) -> list[ExecutionAuthorization]:          return _registry.list_all(limit)
def list_for_mission(mission_id: str, limit: int = 100) -> list:         return _registry.list_for_mission(mission_id, limit)
def list_for_task(task_id: str, limit: int = 100) -> list:               return _registry.list_for_task(task_id, limit)
def list_executable(limit: int = 100) -> list[ExecutionAuthorization]:   return _registry.list_executable(limit)
def count() -> int:                                                       return _registry.count()
def count_by_status(status: AuthorizationStatus) -> int:                 return _registry.count_by_status(status)
def summary_for_mission(mission_id: str) -> dict:                        return _registry.summary_for_mission(mission_id)
def stats() -> dict:                                                      return _registry.stats()
def _reset_for_testing() -> None:                                         _registry._reset_for_testing()
