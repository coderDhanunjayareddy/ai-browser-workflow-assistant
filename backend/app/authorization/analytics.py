"""
V8.8 Execution Authorization Framework — AuthorizationAnalytics.

Thread-safe lifecycle counters for authorization evaluations.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class _AuthorizationCounters:
    authorizations_created:  int   = 0
    authorized:              int   = 0
    denied:                  int   = 0
    expired:                 int   = 0
    revoked:                 int   = 0
    consumed:                int   = 0
    total_eval_ms:           float = 0.0
    eval_count:              int   = 0


_counters = _AuthorizationCounters()
_lock     = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _AuthorizationCounters()


def record_created(authorized: bool, eval_ms: float = 0.0) -> None:
    with _lock:
        _counters.authorizations_created += 1
        if authorized:
            _counters.authorized += 1
        else:
            _counters.denied += 1
        _counters.total_eval_ms += eval_ms
        _counters.eval_count    += 1


def record_expired() -> None:
    with _lock:
        _counters.expired += 1


def record_revoked() -> None:
    with _lock:
        _counters.revoked += 1


def record_consumed() -> None:
    with _lock:
        _counters.consumed += 1


def get_analytics() -> dict:
    with _lock:
        avg = (
            round(_counters.total_eval_ms / _counters.eval_count, 3)
            if _counters.eval_count > 0 else 0.0
        )
        return {
            "authorizations_created":  _counters.authorizations_created,
            "authorized":              _counters.authorized,
            "denied":                  _counters.denied,
            "expired":                 _counters.expired,
            "revoked":                 _counters.revoked,
            "consumed":                _counters.consumed,
            "avg_evaluation_time_ms":  avg,
        }
