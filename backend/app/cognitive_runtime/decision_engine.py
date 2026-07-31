from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cognitive_runtime.clarification import ClarificationEngine
from app.cognitive_runtime.diagnostics import build_diagnostics
from app.cognitive_runtime.models import EvidenceCollection
from app.cognitive_runtime.policy import DecisionPolicy
from app.cognitive_runtime.progress import compute_progress_snapshot
from app.cognitive_runtime.recovery import RecoveryStateEvaluator
from app.cognitive_runtime.replanning import ReplanningEvaluator
from app.cognitive_runtime.recommendations import RecommendationEngine, RecommendationResult
from app.cognitive_runtime.waits import WaitStateEvaluator


@dataclass(frozen=True)
class CognitiveDecisionContext:
    blueprint: Any | None
    readiness: Any | None
    evidence: EvidenceCollection
    policy: DecisionPolicy


class CognitiveDecisionEngine:
    """Computes advisory cognitive decisions. It never executes recommendations."""

    def __init__(self, recommendation_engine: RecommendationEngine | None = None):
        self.recommendation_engine = recommendation_engine or RecommendationEngine()

    def decide(self, context: CognitiveDecisionContext) -> RecommendationResult:
        diagnostics = build_diagnostics(blueprint=context.blueprint, collection=context.evidence)
        wait_state = WaitStateEvaluator().evaluate(context.evidence)
        clarification = ClarificationEngine().evaluate(blueprint=context.blueprint, evidence=context.evidence)
        recovery = RecoveryStateEvaluator().evaluate(context.evidence)
        replanning = ReplanningEvaluator().evaluate(
            context.evidence,
            contradiction_count=len(diagnostics.contradictions),
        )
        progress = compute_progress_snapshot(
            blueprint=context.blueprint,
            evidence=list(context.evidence.evidence),
            readiness=context.readiness,
            ledger_summary={"source": "cognitive_decision_engine", "execution_impact": "none"},
        )
        return self.recommendation_engine.recommend(
            mission_id=context.evidence.mission_id,
            evidence=context.evidence,
            readiness=context.readiness,
            diagnostics=diagnostics,
            wait_state=wait_state,
            clarification=clarification,
            recovery=recovery,
            replanning=replanning,
            progress=progress,
            policy=context.policy,
        )
