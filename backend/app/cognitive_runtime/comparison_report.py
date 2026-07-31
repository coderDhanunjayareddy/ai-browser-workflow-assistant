from __future__ import annotations

from typing import Any

from app.cognitive_runtime.comparison_metrics import compute_comparison_metrics
from app.cognitive_runtime.comparison_models import DecisionComparison


class ComparisonReportBuilder:
    def build(self, *, mission_id: str, comparisons: list[DecisionComparison]) -> dict[str, Any]:
        metrics = compute_comparison_metrics(comparisons)
        disagreements = [item for item in comparisons if item.agreement in {"partial", "disagreement"}]
        return {
            "mission_id": mission_id,
            "summary": {
                "total_comparisons": metrics["total_comparisons"],
                "overall_agreement": metrics["overall_agreement"],
                "high_confidence_disagreement": metrics["high_confidence_disagreement"],
                "average_confidence": metrics["average_confidence"],
                "runtime_boundary": "Runtime V1 always wins; Cognitive Runtime is shadow-only.",
            },
            "per_decision_statistics": metrics["agreement_by_decision_type"],
            "disagreement_hotspots": self._hotspots(disagreements),
            "confidence_histogram_data": metrics["confidence_distribution"],
            "migration_readiness": self._migration_readiness(metrics),
            "metrics": metrics,
        }

    def _hotspots(self, disagreements: list[DecisionComparison]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        examples: dict[str, DecisionComparison] = {}
        for item in disagreements:
            key = f"{item.runtime_decision}->{item.cognitive_decision}"
            counts[key] = counts.get(key, 0) + 1
            examples.setdefault(key, item)
        return [
            {
                "transition": key,
                "count": count,
                "example": examples[key].to_dict(),
            }
            for key, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ]

    def _migration_readiness(self, metrics: dict[str, Any]) -> dict[str, Any]:
        total = metrics["total_comparisons"]
        agreement = metrics["overall_agreement"]
        high_conflict = metrics["high_confidence_disagreement"]
        if total == 0:
            readiness = "insufficient_data"
        elif agreement >= 0.9 and high_conflict == 0:
            readiness = "ready_for_advisory_override_logging"
        elif agreement >= 0.75:
            readiness = "continue_shadow_comparison"
        else:
            readiness = "not_ready_for_adoption"
        return {
            "status": readiness,
            "required_next_step": "Wave 5B advisory override logging",
            "execution_authority": "runtime_v1",
        }
