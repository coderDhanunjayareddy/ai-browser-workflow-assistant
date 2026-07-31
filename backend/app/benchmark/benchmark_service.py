from __future__ import annotations

from statistics import mean
from typing import Any

from app.benchmark.benchmark_catalog import benchmark_catalog, get_benchmark
from app.benchmark.benchmark_export import export_runs
from app.benchmark.benchmark_executor import BenchmarkExecutor
from app.benchmark.benchmark_repository import BenchmarkRepository
from app.benchmark.benchmark_runner import BenchmarkRunner


class BenchmarkService:
    def __init__(self, repository: BenchmarkRepository):
        self.repository = repository

    def catalog(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in benchmark_catalog()]

    def benchmark(self, benchmark_id: str) -> dict[str, Any] | None:
        benchmark = get_benchmark(benchmark_id)
        return benchmark.to_dict() if benchmark else None

    def launch_descriptor(self, benchmark_id: str) -> dict[str, Any] | None:
        benchmark = get_benchmark(benchmark_id)
        return BenchmarkExecutor().launch_descriptor(benchmark) if benchmark else None

    def capture_run(self, benchmark_id: str, *, mission_id: str | None = None, snapshots: dict[str, Any] | None = None):
        benchmark = get_benchmark(benchmark_id)
        if benchmark is None:
            return None
        result = BenchmarkRunner().run(benchmark=benchmark, mission_id=mission_id, snapshots=snapshots)
        return self.repository.save(result)

    def get_run(self, run_id: str):
        return self.repository.get_run(run_id)

    def history(self) -> list[dict[str, Any]]:
        return [run.to_dict() for run in self.repository.list_runs()]

    def report(self, run_id: str) -> dict[str, Any] | None:
        reports = self.repository.reports(run_id)
        if not reports:
            return None
        return reports[0].to_dict()

    def failures(self, run_id: str) -> list[dict[str, Any]]:
        return [failure.to_dict() for failure in self.repository.failures(run_id)]

    def metrics(self) -> dict[str, Any]:
        runs = self.repository.list_runs()
        if not runs:
            return {"run_count": 0, "average_score": 0.0, "mission_success_rate": 0.0}
        return {
            "run_count": len(runs),
            "average_score": round(mean(run.score for run in runs), 4),
            "mission_success_rate": round(mean(float(run.metrics.get("mission_success_rate") or 0.0) for run in runs), 4),
            "average_reliability": round(mean(float(run.metrics.get("reliability_score") or 0.0) for run in runs), 4),
            "average_agreement": round(mean(float(run.metrics.get("agreement_rate") or 0.0) for run in runs), 4),
        }

    def trends(self) -> dict[str, Any]:
        runs = self.repository.list_runs()
        return {
            "available": len(runs) >= 2,
            "run_count": len(runs),
            "scores": [{"run_id": run.run_id, "score": run.score, "timestamp": run.timestamp.isoformat()} for run in runs],
        }

    def export(self) -> dict[str, Any]:
        return export_runs(self.repository.list_runs())
