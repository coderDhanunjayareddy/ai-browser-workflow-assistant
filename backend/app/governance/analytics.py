"""
V8.5 Governance Layer — GovernanceAnalytics.

Thread-safe lifecycle counters for governance contracts.
Reuses the _Counters + Lock pattern from V6.5/V7.0/V7.5/V8.0.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class _GovernanceCounters:
    contracts_created:  int   = 0
    contracts_consumed: int   = 0
    contracts_revoked:  int   = 0
    contracts_expired:  int   = 0
    # running average age: from created_at to consumed/revoked/expired
    total_age_ms: float = 0.0
    age_count:    int   = 0


_counters = _GovernanceCounters()
_lock     = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _GovernanceCounters()


def record_created() -> None:
    with _lock:
        _counters.contracts_created += 1


def record_consumed(age_ms: float = 0.0) -> None:
    with _lock:
        _counters.contracts_consumed += 1
        _counters.total_age_ms += age_ms
        _counters.age_count    += 1


def record_revoked(age_ms: float = 0.0) -> None:
    with _lock:
        _counters.contracts_revoked += 1
        _counters.total_age_ms += age_ms
        _counters.age_count    += 1


def record_expired(age_ms: float = 0.0) -> None:
    with _lock:
        _counters.contracts_expired += 1
        _counters.total_age_ms += age_ms
        _counters.age_count    += 1


def get_analytics() -> dict:
    with _lock:
        avg_age = (
            round(_counters.total_age_ms / _counters.age_count, 1)
            if _counters.age_count > 0 else 0.0
        )
        base = {
            "contracts_created":  _counters.contracts_created,
            "contracts_consumed": _counters.contracts_consumed,
            "contracts_revoked":  _counters.contracts_revoked,
            "contracts_expired":  _counters.contracts_expired,
            "avg_contract_age_ms": avg_age,
        }
    # live count from registry (no circular import — registry does not import analytics)
    try:
        from app.governance import registry as _reg
        from app.governance.models import ContractStatus
        base["contracts_active"] = _reg.count_by_status(ContractStatus.active)
    except Exception:
        base["contracts_active"] = 0
    return base
