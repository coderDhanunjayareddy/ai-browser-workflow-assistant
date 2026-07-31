from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cognitive_runtime.confidence_engine import DecisionConfidenceEngine
from app.cognitive_runtime.decision_models import CognitiveDecision, CognitiveDecisionType, DecisionSignal
from app.cognitive_runtime.decision_rules import DeclarativeDecisionRuleSet
from app.cognitive_runtime.explanations import DecisionExplanation, DecisionExplanationBuilder
from app.cognitive_runtime.models import EvidenceCollection
from app.cognitive_runtime.policy import DecisionPolicy
from app.cognitive_runtime.priority import PriorityEvaluator


@dataclass(frozen=True)
class RecommendationResult:
    decision: CognitiveDecision
    explanation: DecisionExplanation
    ranked_signals: list[dict[str, Any]]


class RecommendationEngine:
    """Produces advisory recommendations from cognitive diagnostics."""

    def __init__(
        self,
        *,
        rules: DeclarativeDecisionRuleSet | None = None,
        priority: PriorityEvaluator | None = None,
        confidence: DecisionConfidenceEngine | None = None,
        explanations: DecisionExplanationBuilder | None = None,
    ):
        self.rules = rules or DeclarativeDecisionRuleSet()
        self.priority = priority or PriorityEvaluator()
        self.confidence = confidence or DecisionConfidenceEngine()
        self.explanations = explanations or DecisionExplanationBuilder()

    def recommend(
        self,
        *,
        mission_id: str,
        evidence: EvidenceCollection,
        readiness: Any | None,
        diagnostics: Any | None,
        wait_state: Any | None,
        clarification: Any | None,
        recovery: Any | None,
        replanning: Any | None,
        progress: Any | None,
        policy: DecisionPolicy | None = None,
    ) -> RecommendationResult:
        policy = policy or DecisionPolicy()
        signals = self.rules.evaluate(
            readiness=readiness,
            diagnostics=diagnostics,
            wait_state=wait_state,
            clarification=clarification,
            recovery=recovery,
            replanning=replanning,
            progress=progress,
        )
        ranked = self.priority.rank(signals, policy)
        winning_signal = ranked[0][0] if ranked else DecisionSignal(CognitiveDecisionType.UNKNOWN, 0.3, "no_signal")
        score = self.confidence.score(
            evidence=evidence,
            diagnostics=diagnostics,
            readiness=readiness,
            clarification=clarification,
            progress=progress,
        )
        alternatives = [
            {"decision_type": signal.decision_type.value, "score": priority_score, "reason": reason}
            for signal, priority_score, reason in ranked[1:]
        ]
        rejected = [
            {"decision_type": signal.decision_type.value, "reason": signal.reason}
            for signal, _, _ in ranked
            if signal.decision_type != winning_signal.decision_type
        ]
        decision = CognitiveDecision(
            mission_id=mission_id,
            decision_type=winning_signal.decision_type,
            confidence=round(score.normalized_score * winning_signal.strength, 4),
            rationale=[winning_signal.reason],
            alternatives=alternatives,
            rejected_decisions=rejected,
            policy=policy.name,
            metadata={"shadow_only": True, "execution_impact": "none", "confidence": score.to_dict()},
        )
        explanation = self.explanations.build(
            decision=decision,
            winning_signal=winning_signal,
            confidence=score,
            diagnostics=diagnostics,
        )
        return RecommendationResult(
            decision=decision,
            explanation=explanation,
            ranked_signals=[
                {"signal": signal.to_dict(), "priority_score": priority_score, "ranking_reason": reason}
                for signal, priority_score, reason in ranked
            ],
        )
