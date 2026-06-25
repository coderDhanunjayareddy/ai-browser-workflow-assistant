"""
V7.5 Decision Center — DecisionAnalytics.

Thread-safe counters for decision lifecycle metrics.
Reuses the analytics-counter pattern from V6.5 TrustAnalytics and V7.0 BrowserEventAnalytics.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class _DecisionCounters:
    created:        int   = 0
    acknowledged:   int   = 0
    dismissed:      int   = 0
    resolved:       int   = 0
    critical:       int   = 0
    high:           int   = 0
    medium:         int   = 0
    low:            int   = 0
    # running average for resolution time
    total_resolution_ms: float = 0.0
    resolution_count:    int   = 0


_counters = _DecisionCounters()
_lock     = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _DecisionCounters()


def record_created(priority: str) -> None:
    with _lock:
        _counters.created += 1
        p = priority.upper()
        if p == "CRITICAL": _counters.critical += 1
        elif p == "HIGH":   _counters.high     += 1
        elif p == "MEDIUM": _counters.medium   += 1
        else:               _counters.low      += 1


def record_acknowledged() -> None:
    with _lock:
        _counters.acknowledged += 1


def record_dismissed() -> None:
    with _lock:
        _counters.dismissed += 1


def record_resolved(duration_ms: float = 0.0) -> None:
    with _lock:
        _counters.resolved += 1
        _counters.total_resolution_ms += duration_ms
        _counters.resolution_count    += 1


def get_analytics() -> dict:
    with _lock:
        avg_res = (
            round(_counters.total_resolution_ms / _counters.resolution_count, 1)
            if _counters.resolution_count > 0 else 0.0
        )
        return {
            "created":              _counters.created,
            "acknowledged":         _counters.acknowledged,
            "dismissed":            _counters.dismissed,
            "resolved":             _counters.resolved,
            "critical":             _counters.critical,
            "high":                 _counters.high,
            "medium":               _counters.medium,
            "low":                  _counters.low,
            "avg_resolution_ms":    avg_res,
        }
