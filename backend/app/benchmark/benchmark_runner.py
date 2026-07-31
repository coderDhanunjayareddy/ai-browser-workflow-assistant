from __future__ import annotations

from time import perf_counter
from typing import Any

from app.benchmark.benchmark_diagnostics import FailureClassifier
from app.benchmark.benchmark_metrics import compute_metrics
from app.benchmark.benchmark_models import BenchmarkMission, BenchmarkRunResult
from app.benchmark.benchmark_reports import BenchmarkReportBuilder
from app.benchmark.benchmark_score import benchmark_score
from app.benchmark.benchmark_trace import ExecutionTraceCollector
from app.benchmark.benchmark_validator import BenchmarkValidator


class BenchmarkRunner:
    """Runs the passive benchmark evaluation pipeline over provided snapshots."""

    def run(self, *, benchmark: BenchmarkMission, mission_id: str | None = None, snapshots: dict[str, Any] | None = None) -> BenchmarkRunResult:
        started = perf_counter()
        trace = ExecutionTraceCollector().collect(benchmark=benchmark, mission_id=mission_id, snapshots=snapshots)
        validation = BenchmarkValidator().validate(benchmark=benchmark, trace=trace)
        metrics = compute_metrics(benchmark=benchmark, trace=trace)
        metrics["validation_accuracy"] = 1.0 if validation["valid"] else metrics["validation_accuracy"]
        score = benchmark_score(metrics)
        failures = FailureClassifier().classify(trace, metrics)
        run_id = f"benchmark_run_{trace.trace_id.removeprefix('benchmark_trace_')}"
        reports = BenchmarkReportBuilder().build(
            run_id=run_id,
            benchmark=benchmark,
            trace=trace,
            metrics=metrics,
            failures=failures,
            score=score,
        )
        return BenchmarkRunResult(
            run_id=run_id,
            benchmark_id=benchmark.id,
            mission_id=mission_id,
            category=benchmark.category,
            status="failed" if failures else "captured",
            score=score,
            metrics=metrics,
            trace=trace,
            failures=failures,
            reports=reports,
            duration_ms=int((perf_counter() - started) * 1000),
            metadata={"execution_impact": "none", "validation": validation},
        )
