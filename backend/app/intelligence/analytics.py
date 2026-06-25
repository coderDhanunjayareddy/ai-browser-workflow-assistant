"""
V4.0 Intelligence Layer analytics counters.

Thread-safe, in-memory only — resets on server restart.
Follows the same pattern as research/analytics.py and cognitive_core/analytics.py.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

_lock = threading.Lock()


@dataclass
class _IntelligenceCounters:
    opportunities_detected: int = 0
    recommendations_generated: int = 0
    plans_built: int = 0
    bootstrap_generated: int = 0
    # Readiness distribution
    ready_count: int = 0
    partially_ready_count: int = 0
    blocked_count: int = 0
    # Workflow conversions (user clicked "Prepare Workflow")
    workflow_conversions: int = 0
    # Approval distribution
    safe_count: int = 0
    requires_approval_count: int = 0
    high_risk_count: int = 0
    # Research-only (no opportunity detected)
    research_only_count: int = 0


_counters = _IntelligenceCounters()


def record_opportunity_detected() -> None:
    with _lock:
        _counters.opportunities_detected += 1


def record_research_only() -> None:
    with _lock:
        _counters.research_only_count += 1


def record_recommendations(count: int) -> None:
    with _lock:
        _counters.recommendations_generated += count


def record_plan_built() -> None:
    with _lock:
        _counters.plans_built += 1


def record_bootstrap_generated() -> None:
    with _lock:
        _counters.bootstrap_generated += 1


def record_readiness(state: str) -> None:
    with _lock:
        if state == "READY":
            _counters.ready_count += 1
        elif state == "PARTIALLY_READY":
            _counters.partially_ready_count += 1
        else:
            _counters.blocked_count += 1


def record_approval(level: str) -> None:
    with _lock:
        if level == "SAFE":
            _counters.safe_count += 1
        elif level == "REQUIRES_APPROVAL":
            _counters.requires_approval_count += 1
        else:
            _counters.high_risk_count += 1


def record_workflow_conversion() -> None:
    with _lock:
        _counters.workflow_conversions += 1


def get_analytics() -> dict:
    with _lock:
        total = (
            _counters.ready_count
            + _counters.partially_ready_count
            + _counters.blocked_count
        ) or 1
        return {
            "opportunities_detected": _counters.opportunities_detected,
            "research_only_count": _counters.research_only_count,
            "recommendations_generated": _counters.recommendations_generated,
            "plans_built": _counters.plans_built,
            "bootstrap_generated": _counters.bootstrap_generated,
            "workflow_conversions": _counters.workflow_conversions,
            "readiness_distribution": {
                "ready": _counters.ready_count,
                "partially_ready": _counters.partially_ready_count,
                "blocked": _counters.blocked_count,
                "ready_pct": round(_counters.ready_count / total * 100, 1),
                "partially_ready_pct": round(_counters.partially_ready_count / total * 100, 1),
                "blocked_pct": round(_counters.blocked_count / total * 100, 1),
            },
            "approval_distribution": {
                "safe": _counters.safe_count,
                "requires_approval": _counters.requires_approval_count,
                "high_risk": _counters.high_risk_count,
            },
        }


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _IntelligenceCounters()
