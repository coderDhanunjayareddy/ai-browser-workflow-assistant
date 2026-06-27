"""
V8.0 Human Approval Center — ApprovalAnalytics.

Thread-safe lifecycle counters.
Reuses the _Counters + Lock pattern from V6.5/V7.0/V7.5.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class _ApprovalCounters:
    created:   int = 0
    approved:  int = 0
    rejected:  int = 0
    expired:   int = 0
    cancelled: int = 0
    critical:  int = 0
    high:      int = 0
    medium:    int = 0
    low:       int = 0
    # running average approval time (created → approved/rejected)
    total_approval_ms: float = 0.0
    approval_count:    int   = 0


_counters = _ApprovalCounters()
_lock     = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _ApprovalCounters()


def record_created(risk_level: str) -> None:
    with _lock:
        _counters.created += 1
        r = risk_level.upper()
        if r == "CRITICAL": _counters.critical += 1
        elif r == "HIGH":   _counters.high     += 1
        elif r == "MEDIUM": _counters.medium   += 1
        else:               _counters.low      += 1


def record_approved(duration_ms: float = 0.0) -> None:
    with _lock:
        _counters.approved += 1
        _counters.total_approval_ms += duration_ms
        _counters.approval_count    += 1


def record_rejected(duration_ms: float = 0.0) -> None:
    with _lock:
        _counters.rejected += 1
        _counters.total_approval_ms += duration_ms
        _counters.approval_count    += 1


def record_expired() -> None:
    with _lock:
        _counters.expired += 1


def record_cancelled() -> None:
    with _lock:
        _counters.cancelled += 1


def get_analytics() -> dict:
    with _lock:
        avg_ms = (
            round(_counters.total_approval_ms / _counters.approval_count, 1)
            if _counters.approval_count > 0 else 0.0
        )
        return {
            "created":           _counters.created,
            "approved":          _counters.approved,
            "rejected":          _counters.rejected,
            "expired":           _counters.expired,
            "cancelled":         _counters.cancelled,
            "critical":          _counters.critical,
            "high":              _counters.high,
            "medium":            _counters.medium,
            "low":               _counters.low,
            "avg_approval_ms":   avg_ms,
        }
