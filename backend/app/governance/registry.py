"""
V8.5 Governance Layer — ContractRegistry.

In-memory store for GovernanceContracts.
TTL = 604800s (7 days) — contracts outlive approval TTL so execution can consume them.
RLock + monotonic pattern from V6.5/V7.0/V7.5/V8.0.

Auto-expiry: ACTIVE contracts past expires_at transition to EXPIRED on first access.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Optional

from app.governance.models import (
    GovernanceContract, ContractStatus,
)

TTL_SECONDS: int = 604800   # 7 days registry TTL


class ContractRegistry:

    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        # contract_id → (GovernanceContract, inserted_at_monotonic)
        self._contracts:  dict[str, tuple[GovernanceContract, float]] = {}
        # mission_id → set[contract_id]
        self._by_mission: dict[str, set[str]] = defaultdict(set)
        # approval_id → contract_id (one-to-one)
        self._by_approval: dict[str, str] = {}
        self._total_added:   int = 0
        self._total_evicted: int = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _is_ttl_expired(self, inserted_at: float, now: float) -> bool:
        return now - inserted_at > self._ttl

    def _check_contract_expiry(self, item: GovernanceContract) -> None:
        if item.status == ContractStatus.active and time.time() > item.expires_at:
            item.status = ContractStatus.expired

    def _evict(self, contract_id: str, item: GovernanceContract) -> None:
        self._contracts.pop(contract_id, None)
        if item.mission_id:
            self._by_mission[item.mission_id].discard(contract_id)
        self._by_approval.pop(item.approval_id, None)
        self._total_evicted += 1

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, item: GovernanceContract) -> None:
        now = time.monotonic()
        with self._lock:
            self._contracts[item.contract_id] = (item, now)
            if item.mission_id:
                self._by_mission[item.mission_id].add(item.contract_id)
            self._by_approval[item.approval_id] = item.contract_id
            self._total_added += 1

    def get(self, contract_id: str) -> Optional[GovernanceContract]:
        now = time.monotonic()
        with self._lock:
            entry = self._contracts.get(contract_id)
            if entry is None:
                return None
            item, inserted_at = entry
            if self._is_ttl_expired(inserted_at, now):
                self._evict(contract_id, item)
                return None
            self._check_contract_expiry(item)
            return item

    def get_for_approval(self, approval_id: str) -> Optional[GovernanceContract]:
        with self._lock:
            contract_id = self._by_approval.get(approval_id)
        if contract_id is None:
            return None
        return self.get(contract_id)

    def revoke(self, contract_id: str, reason: str = "") -> bool:
        with self._lock:
            entry = self._contracts.get(contract_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != ContractStatus.active:
                return False
            item.status         = ContractStatus.revoked
            item.revoked_at     = time.time()
            item.revoked_reason = reason
            return True

    def expire(self, contract_id: str) -> bool:
        with self._lock:
            entry = self._contracts.get(contract_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != ContractStatus.active:
                return False
            item.status = ContractStatus.expired
            return True

    def consume(self, contract_id: str) -> bool:
        with self._lock:
            entry = self._contracts.get(contract_id)
            if entry is None:
                return False
            item, _ = entry
            if item.status != ContractStatus.active:
                return False
            item.status      = ContractStatus.consumed
            item.consumed_at = time.time()
            return True

    def list_all(self, limit: int = 100) -> list[GovernanceContract]:
        now = time.monotonic()
        with self._lock:
            valid = []
            for item, inserted_at in self._contracts.values():
                if self._is_ttl_expired(inserted_at, now):
                    continue
                self._check_contract_expiry(item)
                valid.append(item)
        valid.sort(key=lambda c: -c.created_at)
        return valid[:limit]

    def list_active(self, limit: int = 100) -> list[GovernanceContract]:
        return [c for c in self.list_all(limit=1000)
                if c.status == ContractStatus.active][:limit]

    def list_for_mission(self, mission_id: str, limit: int = 100) -> list[GovernanceContract]:
        now = time.monotonic()
        with self._lock:
            ids = self._by_mission.get(mission_id, set()).copy()
            out = []
            for cid in ids:
                entry = self._contracts.get(cid)
                if entry is None:
                    continue
                item, inserted_at = entry
                if self._is_ttl_expired(inserted_at, now):
                    self._evict(cid, item)
                    continue
                self._check_contract_expiry(item)
                out.append(item)
        out.sort(key=lambda c: -c.created_at)
        return out[:limit]

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(
                1 for _, inserted_at in self._contracts.values()
                if not self._is_ttl_expired(inserted_at, now)
            )

    def count_by_status(self, status: ContractStatus) -> int:
        return sum(1 for c in self.list_all(limit=10000) if c.status == status)

    def summary_for_mission(self, mission_id: str) -> dict:
        items = self.list_for_mission(mission_id, limit=10000)
        return {
            "total":              len(items),
            "active_contracts":   sum(1 for c in items if c.status == ContractStatus.active),
            "expired_contracts":  sum(1 for c in items if c.status == ContractStatus.expired),
            "revoked_contracts":  sum(1 for c in items if c.status == ContractStatus.revoked),
            "consumed_contracts": sum(1 for c in items if c.status == ContractStatus.consumed),
            "execution_eligible": sum(1 for c in items if c.is_eligible),
        }

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            valid = [(item, ins) for item, ins in self._contracts.values()
                     if not self._is_ttl_expired(ins, now)]
        return {
            "cached_items":   len(valid),
            "total_added":    self._total_added,
            "total_evicted":  self._total_evicted,
            "active_count":   sum(1 for i, _ in valid if i.status == ContractStatus.active),
        }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._contracts.clear()
            self._by_mission.clear()
            self._by_approval.clear()
            self._total_added   = 0
            self._total_evicted = 0


# Module-level singleton
_registry = ContractRegistry()


def add(item: GovernanceContract) -> None:
    _registry.add(item)

def get(contract_id: str) -> Optional[GovernanceContract]:
    return _registry.get(contract_id)

def get_for_approval(approval_id: str) -> Optional[GovernanceContract]:
    return _registry.get_for_approval(approval_id)

def revoke(contract_id: str, reason: str = "") -> bool:
    return _registry.revoke(contract_id, reason)

def expire(contract_id: str) -> bool:
    return _registry.expire(contract_id)

def consume(contract_id: str) -> bool:
    return _registry.consume(contract_id)

def list_all(limit: int = 100) -> list[GovernanceContract]:
    return _registry.list_all(limit)

def list_active(limit: int = 100) -> list[GovernanceContract]:
    return _registry.list_active(limit)

def list_for_mission(mission_id: str, limit: int = 100) -> list[GovernanceContract]:
    return _registry.list_for_mission(mission_id, limit)

def count() -> int:
    return _registry.count()

def count_by_status(status: ContractStatus) -> int:
    return _registry.count_by_status(status)

def summary_for_mission(mission_id: str) -> dict:
    return _registry.summary_for_mission(mission_id)

def stats() -> dict:
    return _registry.stats()

def _reset_for_testing() -> None:
    _registry._reset_for_testing()
