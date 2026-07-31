from __future__ import annotations

import time
from typing import Any

from app.cognitive_runtime.comparison import DecisionAgreementEngine
from app.cognitive_runtime.comparison_explanations import ComparisonExplanationBuilder
from app.cognitive_runtime.comparison_metrics import compute_comparison_metrics
from app.cognitive_runtime.comparison_models import DecisionComparison
from app.cognitive_runtime.comparison_report import ComparisonReportBuilder
from app.cognitive_runtime.comparison_repository import DecisionComparisonRepository
from app.cognitive_runtime.recommendations import RecommendationResult


class DecisionComparisonService:
    """Persists passive Runtime V1 vs Cognitive Runtime decision comparisons."""

    def __init__(
        self,
        repository: DecisionComparisonRepository,
        *,
        agreement: DecisionAgreementEngine | None = None,
        explanations: ComparisonExplanationBuilder | None = None,
    ):
        self.repository = repository
        self.agreement = agreement or DecisionAgreementEngine()
        self.explanations = explanations or ComparisonExplanationBuilder()

    def record(
        self,
        *,
        mission_id: str,
        runtime_decision: str,
        runtime_reason: str,
        cognitive: RecommendationResult,
        intent_id: str | None = None,
        blueprint_node_id: str | None = None,
        recommendation_latency_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DecisionComparison:
        agreement = self.agreement.compare(
            runtime_decision=runtime_decision,
            cognitive_decision=cognitive.decision.decision_type.value,
        )
        cognitive_reason = "; ".join(cognitive.decision.rationale)
        explanation = self.explanations.build(
            agreement=agreement,
            runtime_reason=runtime_reason,
            cognitive_reason=cognitive_reason,
            cognitive_explanation=cognitive.explanation.to_dict(),
        )
        comparison = DecisionComparison(
            mission_id=mission_id,
            intent_id=intent_id,
            blueprint_node_id=blueprint_node_id,
            runtime_decision=agreement.runtime_decision,
            cognitive_decision=agreement.cognitive_decision,
            agreement=agreement.agreement.value,
            confidence=cognitive.decision.confidence,
            runtime_reason=runtime_reason,
            cognitive_reason=cognitive_reason,
            explanation=explanation,
            metadata={
                "shadow_only": True,
                "runtime_v1_wins": True,
                "recommendation_latency_ms": round(float(recommendation_latency_ms or 0.0), 2),
                **dict(metadata or {}),
            },
        )
        return self.repository.save(comparison)

    def latest(self, mission_id: str) -> DecisionComparison | None:
        return self.repository.latest(mission_id)

    def history(self, mission_id: str) -> list[DecisionComparison]:
        return self.repository.history(mission_id)

    def metrics(self, mission_id: str) -> dict[str, Any]:
        return compute_comparison_metrics(self.history(mission_id))

    def report(self, mission_id: str) -> dict[str, Any]:
        return ComparisonReportBuilder().build(mission_id=mission_id, comparisons=self.history(mission_id))

    def disagreements(self, mission_id: str) -> list[DecisionComparison]:
        return self.repository.disagreements(mission_id)


def now_ms() -> float:
    return time.perf_counter() * 1000
