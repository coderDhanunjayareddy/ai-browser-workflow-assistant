from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.decision_models import CognitiveDecision, DecisionSignal
from app.cognitive_runtime.decision_scores import DecisionScoreBreakdown


@dataclass(frozen=True)
class DecisionExplanation:
    why: str
    supporting_evidence: list[str]
    conflicting_evidence: list[str]
    assumptions: list[str]
    confidence_explanation: dict[str, Any]
    alternatives_considered: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionExplanationBuilder:
    """Builds transparent explanations for advisory decisions."""

    def build(
        self,
        *,
        decision: CognitiveDecision,
        winning_signal: DecisionSignal,
        confidence: DecisionScoreBreakdown,
        diagnostics: Any | None,
    ) -> DecisionExplanation:
        contradictions = list(getattr(diagnostics, "contradictions", []) or [])
        return DecisionExplanation(
            why=f"Recommended {decision.decision_type.value} because {winning_signal.reason}.",
            supporting_evidence=list(winning_signal.evidence_refs),
            conflicting_evidence=[
                evidence_id
                for contradiction in contradictions
                for evidence_id in list(contradiction.get("evidence_ids", []) if isinstance(contradiction, dict) else [])
            ],
            assumptions=[
                "Decision is advisory only.",
                "Runtime V1 remains the execution authority.",
                "Mission Completion remains the completion authority.",
            ],
            confidence_explanation=confidence.to_dict(),
            alternatives_considered=decision.alternatives,
        )
