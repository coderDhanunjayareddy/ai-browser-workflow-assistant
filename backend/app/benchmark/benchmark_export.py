from __future__ import annotations

from app.benchmark.benchmark_models import BenchmarkRunResult


def export_runs(runs: list[BenchmarkRunResult]) -> dict:
    return {
        "schema_version": "execution_benchmark_export.v1",
        "run_count": len(runs),
        "runs": [run.to_dict() for run in runs],
    }
