from __future__ import annotations

from app.benchmark.benchmark_models import BenchmarkMission, BenchmarkReport, BenchmarkRunResult, ExecutionTrace, FailureClassification


class BenchmarkReportBuilder:
    def build(
        self,
        *,
        run_id: str,
        benchmark: BenchmarkMission,
        trace: ExecutionTrace,
        metrics: dict,
        failures: list[FailureClassification],
        score: float,
    ) -> list[BenchmarkReport]:
        payload = {
            "mission_report": {
                "benchmark_id": benchmark.id,
                "title": benchmark.title,
                "category": benchmark.category,
                "status": "failed" if failures else "captured",
                "score": score,
            },
            "benchmark_report": {
                "expected_deliverable": benchmark.expected_deliverable,
                "expected_blueprint": benchmark.expected_blueprint,
                "expected_providers": benchmark.expected_providers,
            },
            "failure_report": [failure.to_dict() for failure in failures],
            "metrics_report": metrics,
            "comparison_report": trace.stages.get("decision_comparison") or [],
            "regression_report": {"runtime_v1_unchanged": True, "execution_impact": "none"},
            "trend_report": {"available": False, "reason": "Trend report requires historical benchmark runs."},
        }
        return [
            BenchmarkReport(
                run_id=run_id,
                benchmark_id=benchmark.id,
                json_report=payload,
                markdown_report=self._markdown(benchmark, metrics, failures, score),
            )
        ]

    def _markdown(self, benchmark: BenchmarkMission, metrics: dict, failures: list[FailureClassification], score: float) -> str:
        lines = [
            f"# {benchmark.title}",
            "",
            f"- Benchmark: `{benchmark.id}`",
            f"- Category: `{benchmark.category}`",
            f"- Score: `{score}`",
            f"- Runtime impact: `none`",
            "",
            "## Key Metrics",
        ]
        for key in ("mission_success_rate", "blueprint_accuracy", "intent_expansion_accuracy", "ledger_consistency", "agreement_rate"):
            lines.append(f"- {key}: `{metrics.get(key)}`")
        lines.append("")
        lines.append("## Failures")
        if not failures:
            lines.append("- none")
        for failure in failures:
            lines.append(f"- {failure.affected_subsystem}: {failure.root_cause}")
        return "\n".join(lines)
