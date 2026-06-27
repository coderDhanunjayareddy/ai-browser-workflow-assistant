"""
V9.0 Execution Planning Layer — PlanAnalytics.

Thread-safe counters. Same pattern as the V8.8 AuthorizationAnalytics.

Tracks:
  plans_created
  plans_validated        (validate() runs that returned valid=True)
  validation_failures    (validate() runs that returned valid=False)
  avg_steps              (running average of estimated_steps across created plans)
  avg_duration           (running average of estimated_duration_ms across created plans)
  rollback_supported     (count of created plans with rollback_supported=True)
"""
from __future__ import annotations

import threading

_lock = threading.Lock()


class _PlanCounters:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.plans_created:        int = 0
        self.plans_validated:      int = 0
        self.validation_failures:  int = 0
        self.total_steps:          int = 0
        self.total_duration_ms:    int = 0
        self.rollback_supported:   int = 0
        self.archived:             int = 0


_counters = _PlanCounters()


def _reset_for_testing() -> None:
    with _lock:
        _counters.reset()


def record_created(estimated_steps: int, estimated_duration_ms: int, rollback_supported: bool) -> None:
    with _lock:
        _counters.plans_created     += 1
        _counters.total_steps       += estimated_steps
        _counters.total_duration_ms += estimated_duration_ms
        if rollback_supported:
            _counters.rollback_supported += 1


def record_validated(valid: bool) -> None:
    with _lock:
        if valid:
            _counters.plans_validated += 1
        else:
            _counters.validation_failures += 1


def record_archived() -> None:
    with _lock:
        _counters.archived += 1


def get_analytics() -> dict:
    with _lock:
        created = _counters.plans_created
        avg_steps    = round(_counters.total_steps / created, 4) if created else 0.0
        avg_duration = round(_counters.total_duration_ms / created, 4) if created else 0.0
        return {
            "plans_created":       _counters.plans_created,
            "plans_validated":     _counters.plans_validated,
            "validation_failures": _counters.validation_failures,
            "avg_steps":           avg_steps,
            "avg_duration_ms":     avg_duration,
            "rollback_supported":  _counters.rollback_supported,
            "archived":            _counters.archived,
        }
