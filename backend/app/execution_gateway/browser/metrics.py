"""
Phase D — ExecutionMetrics.

Aggregate execution analytics: average retries, recovery success %, validation
success %, locator-strategy distribution, average execution time, step success rate,
and failure distribution.

Thread-safe counters. Additive; best-effort writes never affect execution.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()


class _Counters:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.steps_total:          int   = 0
        self.steps_succeeded:      int   = 0
        self.steps_failed:         int   = 0
        self.retries_total:        int   = 0
        self.recoveries_attempted: int   = 0
        self.recoveries_succeeded: int   = 0
        self.validations_attempted: int  = 0
        self.validations_passed:   int   = 0
        self.exec_time_total_ms:   float = 0.0
        self.locator_strategy:     dict[str, int] = {}
        self.failure_distribution: dict[str, int] = {}
        self.capability_counts:    dict[str, dict[str, int]] = {}


_c = _Counters()


def _reset_for_testing() -> None:
    with _lock:
        _c.reset()


def record_step(*, succeeded: bool, retries: int, elapsed_ms: float,
                locator_strategy: str | None = None) -> None:
    with _lock:
        _c.steps_total += 1
        if succeeded:
            _c.steps_succeeded += 1
        else:
            _c.steps_failed += 1
        _c.retries_total += max(0, retries)
        _c.exec_time_total_ms += max(0.0, elapsed_ms)
        if locator_strategy:
            _c.locator_strategy[locator_strategy] = _c.locator_strategy.get(locator_strategy, 0) + 1


def record_recovery(*, succeeded: bool) -> None:
    with _lock:
        _c.recoveries_attempted += 1
        if succeeded:
            _c.recoveries_succeeded += 1


def record_validation(*, passed: bool) -> None:
    with _lock:
        _c.validations_attempted += 1
        if passed:
            _c.validations_passed += 1


def record_failure(category: str) -> None:
    with _lock:
        _c.failure_distribution[category] = _c.failure_distribution.get(category, 0) + 1


def record_capability(capability_id: str, *, succeeded: bool) -> None:
    with _lock:
        counts = _c.capability_counts.setdefault(capability_id, {"attempted": 0, "succeeded": 0, "failed": 0})
        counts["attempted"] += 1
        if succeeded:
            counts["succeeded"] += 1
        else:
            counts["failed"] += 1


def get_metrics() -> dict:
    with _lock:
        steps = _c.steps_total
        avg_retries  = round(_c.retries_total / steps, 4) if steps else 0.0
        avg_time     = round(_c.exec_time_total_ms / steps, 4) if steps else 0.0
        step_success = round(_c.steps_succeeded / steps, 4) if steps else 0.0
        rec_rate = round(_c.recoveries_succeeded / _c.recoveries_attempted, 4) if _c.recoveries_attempted else 0.0
        val_rate = round(_c.validations_passed / _c.validations_attempted, 4) if _c.validations_attempted else 0.0
        total_strat = sum(_c.locator_strategy.values())
        strat_pct = {k: round(v / total_strat, 4) for k, v in _c.locator_strategy.items()} if total_strat else {}
        return {
            "steps_total":            _c.steps_total,
            "steps_succeeded":        _c.steps_succeeded,
            "steps_failed":           _c.steps_failed,
            "step_success_rate":      step_success,
            "average_retries":        avg_retries,
            "average_execution_ms":   avg_time,
            "recoveries_attempted":   _c.recoveries_attempted,
            "recoveries_succeeded":   _c.recoveries_succeeded,
            "recovery_success_rate":  rec_rate,
            "validations_attempted":  _c.validations_attempted,
            "validations_passed":     _c.validations_passed,
            "validation_success_rate": val_rate,
            "locator_strategy_counts": dict(_c.locator_strategy),
            "locator_strategy_pct":    strat_pct,
            "failure_distribution":    dict(_c.failure_distribution),
            "capability_counts":       {k: dict(v) for k, v in _c.capability_counts.items()},
        }
