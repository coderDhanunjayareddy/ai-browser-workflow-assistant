"""
Phase D — ExecutionMonitor.

Tracks every executing step: start/finish time, retries, validation result,
screenshots, elapsed time, failure category, recovery used, locator strategy.

Per-execution list of StepMonitorRecord, queryable for inspector/diagnostics APIs.
Thread-safe; additive (writes are best-effort and never affect execution).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StepMonitorRecord:
    execution_id:     str
    step_id:          str
    order:            int
    phase:            str
    started_at:       float
    finished_at:      Optional[float] = None
    elapsed_ms:       float           = 0.0
    attempts:         int             = 0
    retries:          int             = 0
    validation_result: Optional[bool] = None
    failure_category: Optional[str]   = None
    recovery_used:    list[str]       = field(default_factory=list)
    locator_strategy: Optional[str]   = None
    screenshots:      list[str]       = field(default_factory=list)
    outcome:          Optional[str]   = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id":      self.execution_id,
            "step_id":           self.step_id,
            "order":             self.order,
            "phase":             self.phase,
            "started_at":        self.started_at,
            "finished_at":       self.finished_at,
            "elapsed_ms":        self.elapsed_ms,
            "attempts":          self.attempts,
            "retries":           self.retries,
            "validation_result": self.validation_result,
            "failure_category":  self.failure_category,
            "recovery_used":     self.recovery_used,
            "locator_strategy":  self.locator_strategy,
            "screenshots":       len(self.screenshots),
            "outcome":           self.outcome,
        }


class ExecutionMonitor:

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_exec: dict[str, list[StepMonitorRecord]] = {}

    def start_step(self, execution_id: str, step_id: str, order: int, phase: str,
                   started_at: float) -> StepMonitorRecord:
        rec = StepMonitorRecord(execution_id=execution_id, step_id=step_id, order=order,
                                phase=phase, started_at=started_at)
        with self._lock:
            self._by_exec.setdefault(execution_id, []).append(rec)
        return rec

    def finish_step(self, rec: StepMonitorRecord, *, finished_at: float, attempts: int,
                    outcome: str, validation_result: Optional[bool] = None,
                    failure_category: Optional[str] = None,
                    locator_strategy: Optional[str] = None,
                    recovery_used: Optional[list[str]] = None,
                    screenshots: Optional[list[str]] = None) -> None:
        with self._lock:
            rec.finished_at = finished_at
            rec.elapsed_ms = round((finished_at - rec.started_at) * 1000, 3)
            rec.attempts = attempts
            rec.retries = max(0, attempts - 1)
            rec.outcome = outcome
            rec.validation_result = validation_result
            rec.failure_category = failure_category
            rec.locator_strategy = locator_strategy
            if recovery_used:
                rec.recovery_used = list(recovery_used)
            if screenshots:
                rec.screenshots = list(screenshots)

    def steps_for(self, execution_id: str) -> list[StepMonitorRecord]:
        with self._lock:
            return list(self._by_exec.get(execution_id, []))

    def current_step(self, execution_id: str) -> Optional[StepMonitorRecord]:
        with self._lock:
            steps = self._by_exec.get(execution_id, [])
            for s in reversed(steps):
                if s.finished_at is None:
                    return s
            return steps[-1] if steps else None

    def summary(self, execution_id: str) -> dict:
        steps = self.steps_for(execution_id)
        completed = [s for s in steps if s.outcome == "completed"]
        failed = [s for s in steps if s.outcome == "failed"]
        return {
            "execution_id":     execution_id,
            "total_steps":      len(steps),
            "completed_steps":  len(completed),
            "failed_steps":     len(failed),
            "total_retries":    sum(s.retries for s in steps),
            "recoveries_used":  sum(len(s.recovery_used) for s in steps),
            "validations":      sum(1 for s in steps if s.validation_result is not None),
            "steps":            [s.to_dict() for s in steps],
        }

    def stats(self) -> dict:
        with self._lock:
            return {
                "tracked_executions": len(self._by_exec),
                "tracked_steps":      sum(len(v) for v in self._by_exec.values()),
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._by_exec.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_monitor = ExecutionMonitor()


def start_step(execution_id: str, step_id: str, order: int, phase: str, started_at: float) -> StepMonitorRecord:
    return _monitor.start_step(execution_id, step_id, order, phase, started_at)

def finish_step(rec: StepMonitorRecord, **kwargs) -> None:
    _monitor.finish_step(rec, **kwargs)

def steps_for(execution_id: str) -> list[StepMonitorRecord]:
    return _monitor.steps_for(execution_id)

def current_step(execution_id: str):
    return _monitor.current_step(execution_id)

def summary(execution_id: str) -> dict:
    return _monitor.summary(execution_id)

def stats() -> dict:
    return _monitor.stats()

def _reset_for_testing() -> None:
    _monitor._reset_for_testing()
