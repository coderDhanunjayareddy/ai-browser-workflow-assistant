from __future__ import annotations

from app.validation.benchmark_diagnostics import diagnose_benchmark
from app.validation.benchmark_metrics import compute_benchmark_metrics
from app.validation.benchmark_models import BenchmarkRunInput, BenchmarkRunResult
from app.validation.benchmark_report import BenchmarkReportBuilder
from app.validation.benchmark_score import score_benchmark


class BenchmarkRunner:
    """Passive benchmark evaluator. It never executes runtime providers."""

    def run(self, run_input: BenchmarkRunInput) -> BenchmarkRunResult:
        snapshot = {
            **dict(run_input.runtime_snapshot),
            "cognitive": dict(run_input.cognitive_snapshot),
            "comparisons": list(run_input.comparison_snapshot.get("comparisons") or []),
        }
        metrics = compute_benchmark_metrics(snapshot)
        diagnostics = diagnose_benchmark(metrics, snapshot)
        score = score_benchmark(metrics)
        report = BenchmarkReportBuilder().build(
            benchmark=run_input.benchmark.to_dict(),
            metrics=metrics,
            diagnostics=diagnostics,
            comparisons=snapshot["comparisons"],
        )
        report["mission_report"]["score"] = score
        return BenchmarkRunResult(
            benchmark_id=run_input.benchmark.benchmark_id,
            category=run_input.benchmark.category,
            mission_id=run_input.mission_id,
            status="evaluated",
            score=score,
            metrics=metrics,
            diagnostics=diagnostics,
            report=report,
        )
