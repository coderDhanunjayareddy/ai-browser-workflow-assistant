from __future__ import annotations

from app.contracts.capabilities import CapabilityHealth


def available_health(run_id: str = "capability-platform") -> CapabilityHealth:
    return CapabilityHealth(run_id=run_id, status="available")


def degraded_health(reason: str, run_id: str = "capability-platform") -> CapabilityHealth:
    return CapabilityHealth(run_id=run_id, status="degraded", reason=reason)
