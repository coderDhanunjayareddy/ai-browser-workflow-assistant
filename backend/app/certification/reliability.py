"""
Phase F — Reliability metrics.

Workflow-level reliability rollup: overall + per-category workflow success rate, duration
percentiles (p50/p95/p99), and semantic-analysis latency percentiles. MERGES (does not
duplicate) the existing Phase D per-step ExecutionMetrics (step/recovery/validation/
locator-strategy/failure distribution).

Thread-safe; deterministic given the same recorded outcomes.
"""
from __future__ import annotations

import threading
from typing import Any

from app.certification.models import WorkflowOutcome


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (deterministic; no numpy)."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 4)
    k = (pct / 100.0) * (len(s) - 1)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 4)


class ReliabilityRegister:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._outcomes: list[WorkflowOutcome] = []
        self._semantic_latencies: list[float] = []

    def record_workflow(self, outcome: WorkflowOutcome) -> None:
        with self._lock:
            self._outcomes.append(outcome)

    def record_semantic_latency(self, ms: float) -> None:
        with self._lock:
            self._semantic_latencies.append(max(0.0, ms))

    def _durations(self) -> list[float]:
        return [o.duration_ms for o in self._outcomes]

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            outcomes = list(self._outcomes)
            sem = list(self._semantic_latencies)

        total = len(outcomes)
        passed = sum(1 for o in outcomes if o.passed)
        durations = [o.duration_ms for o in outcomes]

        # per-category rollup
        by_cat: dict[str, dict[str, Any]] = {}
        for o in outcomes:
            c = by_cat.setdefault(o.category, {"total": 0, "passed": 0, "durations": []})
            c["total"] += 1
            c["passed"] += 1 if o.passed else 0
            c["durations"].append(o.duration_ms)
        category_success = {
            cat: {
                "total": d["total"],
                "passed": d["passed"],
                "success_rate": round(d["passed"] / d["total"], 4) if d["total"] else 0.0,
                "p50_ms": percentile(d["durations"], 50),
                "p95_ms": percentile(d["durations"], 95),
            }
            for cat, d in sorted(by_cat.items())
        }

        # merge the existing Phase D per-step metrics (best-effort; never fail)
        step_metrics: dict[str, Any] = {}
        try:
            from app.execution_gateway.browser import metrics as exec_metrics
            step_metrics = exec_metrics.get_metrics()
        except Exception:
            step_metrics = {}

        return {
            "workflows_total":        total,
            "workflows_passed":       passed,
            "workflows_failed":       total - passed,
            "workflow_success_rate":  round(passed / total, 4) if total else 0.0,
            "duration_ms": {
                "p50": percentile(durations, 50),
                "p95": percentile(durations, 95),
                "p99": percentile(durations, 99),
                "max": round(max(durations), 4) if durations else 0.0,
                "avg": round(sum(durations) / total, 4) if total else 0.0,
            },
            "semantic_analysis_ms": {
                "samples": len(sem),
                "p50": percentile(sem, 50),
                "p95": percentile(sem, 95),
                "p99": percentile(sem, 99),
            },
            "category_success":       category_success,
            "step_metrics":           step_metrics,
        }

    def outcomes(self) -> list[dict]:
        with self._lock:
            return [o.to_dict() for o in self._outcomes]

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._outcomes.clear()
            self._semantic_latencies.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_register = ReliabilityRegister()


def record_workflow(outcome: WorkflowOutcome) -> None:
    _register.record_workflow(outcome)

def record_semantic_latency(ms: float) -> None:
    _register.record_semantic_latency(ms)

def metrics() -> dict[str, Any]:
    return _register.metrics()

def outcomes() -> list[dict]:
    return _register.outcomes()

def _reset_for_testing() -> None:
    _register._reset_for_testing()
