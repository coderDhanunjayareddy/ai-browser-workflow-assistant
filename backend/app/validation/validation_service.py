from __future__ import annotations

from typing import Any

from app.validation.benchmark_catalog import benchmark_catalog, get_benchmark
from app.validation.benchmark_metrics import compute_benchmark_metrics
from app.validation.benchmark_models import BenchmarkRunInput
from app.validation.benchmark_repository import BenchmarkRepository
from app.validation.benchmark_runner import BenchmarkRunner
from app.validation.benchmark_diagnostics import diagnose_benchmark
from app.validation.benchmark_report import BenchmarkReportBuilder
from app.validation.migration_readiness import MigrationReadinessEvaluator
from app.validation.quality_gates import QualityGateEvaluator


class ValidationService:
    def __init__(self, repository: BenchmarkRepository):
        self.repository = repository

    def benchmarks(self) -> list[dict[str, Any]]:
        return [benchmark.to_dict() for benchmark in benchmark_catalog()]

    def benchmark(self, benchmark_id: str) -> dict[str, Any] | None:
        benchmark = get_benchmark(benchmark_id)
        return benchmark.to_dict() if benchmark else None

    def evaluate_catalog(self) -> list[dict[str, Any]]:
        results = []
        for benchmark in benchmark_catalog():
            result = BenchmarkRunner().run(
                BenchmarkRunInput(
                    benchmark=benchmark,
                    runtime_snapshot=_default_snapshot(benchmark),
                    comparison_snapshot={"comparisons": []},
                )
            )
            results.append(self.repository.save(result).to_dict())
        return results

    def latest_runs(self) -> list[dict[str, Any]]:
        return [run.to_dict() for run in self.repository.list_runs()]

    def metrics(self) -> dict[str, Any]:
        runs = self.repository.list_runs()
        if not runs:
            return compute_benchmark_metrics(_default_snapshot(None))
        return _aggregate_metrics([run.metrics for run in runs])

    def diagnostics(self) -> dict[str, Any]:
        metrics = self.metrics()
        return diagnose_benchmark(metrics, {"ledger": {"intent_count": int(metrics.get("ledger_intents") or 0)}})

    def report(self) -> dict[str, Any]:
        metrics = self.metrics()
        diagnostics = self.diagnostics()
        return BenchmarkReportBuilder().build(
            benchmark={"benchmark_id": "catalog", "category": "all", "mission": "Validation catalog", "expected_outcome": "quality measured"},
            metrics=metrics,
            diagnostics=diagnostics,
            comparisons=[],
        )

    def migration(self) -> dict[str, Any]:
        return MigrationReadinessEvaluator().evaluate(self.metrics(), [])

    def readiness(self) -> dict[str, Any]:
        return {"migration_readiness": self.migration(), "quality": self.quality()}

    def quality(self) -> dict[str, Any]:
        return QualityGateEvaluator().evaluate(self.metrics())


def _default_snapshot(benchmark) -> dict[str, Any]:
    nodes = getattr(benchmark, "expected_blueprint_structure", []) if benchmark else []
    return {
        "mission_completed": False,
        "planner_calls": 0,
        "ledger": {"intent_count": 0, "browser_intents": 0},
        "providers": {},
        "evidence": {"coverage": 0.0, "confidence": 0.0},
        "blueprint": {"readiness": 0.0, "nodes": nodes},
        "validation_accuracy": 0.0,
        "runtime_stability": 1.0,
    }


def _aggregate_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    keys = set().union(*(item.keys() for item in items))
    aggregate: dict[str, Any] = {}
    for key in keys:
        values = [float(item.get(key) or 0.0) for item in items if isinstance(item.get(key), (int, float))]
        aggregate[key] = round(sum(values) / len(values), 4) if values else 0.0
    aggregate["benchmark_runs"] = len(items)
    return aggregate
