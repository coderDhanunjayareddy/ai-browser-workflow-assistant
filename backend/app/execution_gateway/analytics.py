"""
Phase B — Execution Gateway V1 — GatewayAnalytics.

Thread-safe counters. Same pattern as the other V8.x/V9.0 analytics modules.

Tracks:
  executions_started
  executions_completed
  executions_failed
  executions_aborted
  steps_executed
  steps_failed
  total_retries
  rollbacks_performed
  total_duration_ms     (sum of simulated step durations across executions)
"""
from __future__ import annotations

import threading

_lock = threading.Lock()


class _GatewayCounters:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.executions_started:   int   = 0
        self.executions_completed: int   = 0
        self.executions_failed:    int   = 0
        self.executions_aborted:   int   = 0
        self.steps_executed:       int   = 0
        self.steps_failed:         int   = 0
        self.total_retries:        int   = 0
        self.rollbacks_performed:  int   = 0
        self.total_duration_ms:    float = 0.0


_counters = _GatewayCounters()


def _reset_for_testing() -> None:
    with _lock:
        _counters.reset()


def record_started() -> None:
    with _lock:
        _counters.executions_started += 1


def record_finished(
    *,
    state:            str,
    steps_executed:   int,
    steps_failed:     int,
    retries:          int,
    rollbacks:        int,
    duration_ms:      float,
) -> None:
    with _lock:
        if state == "COMPLETED":
            _counters.executions_completed += 1
        elif state == "FAILED":
            _counters.executions_failed += 1
        elif state == "ABORTED":
            _counters.executions_aborted += 1
        _counters.steps_executed      += steps_executed
        _counters.steps_failed        += steps_failed
        _counters.total_retries       += retries
        _counters.rollbacks_performed += rollbacks
        _counters.total_duration_ms   += duration_ms


def get_analytics() -> dict:
    with _lock:
        started = _counters.executions_started
        finished = (_counters.executions_completed + _counters.executions_failed
                    + _counters.executions_aborted)
        avg_steps = round(_counters.steps_executed / finished, 4) if finished else 0.0
        avg_duration = round(_counters.total_duration_ms / finished, 4) if finished else 0.0
        success_rate = round(_counters.executions_completed / finished, 4) if finished else 0.0
        return {
            "executions_started":   _counters.executions_started,
            "executions_completed": _counters.executions_completed,
            "executions_failed":    _counters.executions_failed,
            "executions_aborted":   _counters.executions_aborted,
            "steps_executed":       _counters.steps_executed,
            "steps_failed":         _counters.steps_failed,
            "total_retries":        _counters.total_retries,
            "rollbacks_performed":  _counters.rollbacks_performed,
            "total_duration_ms":    round(_counters.total_duration_ms, 4),
            "avg_steps_per_execution": avg_steps,
            "avg_duration_ms":      avg_duration,
            "success_rate":         success_rate,
        }
