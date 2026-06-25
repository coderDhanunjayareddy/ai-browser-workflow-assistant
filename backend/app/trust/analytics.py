"""
V6.5 Trust Engine — TrustAnalytics.

Thread-safe counters for trust-layer metrics.
Follows the same pattern as app/mission/intelligence/analytics.py.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from app.trust.models import RiskLevel


@dataclass
class _TrustCounters:
    trust_evaluations:    int = 0
    low_risk:             int = 0
    medium_risk:          int = 0
    high_risk:            int = 0
    critical_risk:        int = 0
    approval_recommended: int = 0
    approval_required:    int = 0     # HIGH + CRITICAL (always True)
    total_trust_score:    float = 0.0
    run_count:            int = 0


_counters = _TrustCounters()
_lock = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _TrustCounters()


def record_evaluation(risk_level: RiskLevel, approval_required: bool) -> None:
    with _lock:
        _counters.trust_evaluations += 1
        if risk_level == RiskLevel.low:
            _counters.low_risk += 1
        elif risk_level == RiskLevel.medium:
            _counters.medium_risk += 1
        elif risk_level == RiskLevel.high:
            _counters.high_risk += 1
            _counters.approval_required += 1
        elif risk_level == RiskLevel.critical:
            _counters.critical_risk += 1
            _counters.approval_required += 1
        if approval_required:
            _counters.approval_recommended += 1


def record_trust_score(score: float) -> None:
    with _lock:
        _counters.total_trust_score += score
        _counters.run_count         += 1


def get_analytics() -> dict:
    with _lock:
        avg_score = (
            round(_counters.total_trust_score / _counters.run_count, 3)
            if _counters.run_count > 0 else 0.0
        )
        return {
            "trust_evaluations":    _counters.trust_evaluations,
            "low_risk":             _counters.low_risk,
            "medium_risk":          _counters.medium_risk,
            "high_risk":            _counters.high_risk,
            "critical_risk":        _counters.critical_risk,
            "approval_recommended": _counters.approval_recommended,
            "approval_required":    _counters.approval_required,
            "avg_trust_score":      avg_score,
        }
