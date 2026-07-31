from __future__ import annotations

from typing import Any

from app.validation.migration_readiness import MigrationReadinessEvaluator
from app.validation.quality_gates import QualityGateEvaluator


class BenchmarkReportBuilder:
    def build(self, *, benchmark: dict[str, Any], metrics: dict[str, Any], diagnostics: dict[str, Any], comparisons: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        readiness = MigrationReadinessEvaluator().evaluate(metrics, comparisons)
        quality = QualityGateEvaluator().evaluate(metrics)
        return {
            "mission_report": {
                "benchmark_id": benchmark.get("benchmark_id"),
                "category": benchmark.get("category"),
                "mission": benchmark.get("mission"),
                "expected_outcome": benchmark.get("expected_outcome"),
                "score": None,
            },
            "subsystem_report": diagnostics.get("subsystems", {}),
            "decision_report": {
                "comparison_agreement": metrics.get("comparison_agreement"),
                "decision_confidence": metrics.get("decision_confidence"),
                "high_confidence_disagreement": metrics.get("high_confidence_disagreement"),
            },
            "migration_report": readiness,
            "benchmark_summary": {
                "metrics": metrics,
                "root_cause": diagnostics.get("root_cause"),
                "weak_subsystem": diagnostics.get("weak_subsystem"),
            },
            "regression_summary": {
                "runtime_v1_unchanged": True,
                "execution_impact": "none",
            },
            "trend_report": {
                "available": False,
                "reason": "Trend analysis requires multiple persisted runs.",
            },
            "readiness_report": {
                "quality_gates": quality,
                "migration_readiness": readiness,
            },
        }
