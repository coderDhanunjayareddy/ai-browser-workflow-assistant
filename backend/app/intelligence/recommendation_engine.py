"""
V4.0 Component 5 — WorkflowRecommendationEngine.

Converts an ExecutionPlan into 1–3 human-readable WorkflowRecommendations
that appear in the UI's "Recommended Actions" section.

Rules:
  - Always generate the primary recommendation (launch/prepare workflow).
  - If there are missing inputs → add a "Fill missing info" recommendation.
  - If readiness score > 0.7 → add a "Research more" follow-up recommendation.
  - Maximum 3 recommendations total.
"""
from __future__ import annotations

import uuid

from app.intelligence.models import (
    ApprovalLevel,
    ExecutionPlan,
    ReadinessState,
    WorkflowRecommendation,
    WorkflowReadiness,
)

# Human-readable action labels per readiness state
_PRIMARY_ACTION: dict[ReadinessState, str] = {
    ReadinessState.ready: "Prepare workflow",
    ReadinessState.partially_ready: "Prepare workflow (partial context)",
    ReadinessState.blocked: "Provide missing information first",
}


class WorkflowRecommendationEngine:
    """
    Generates a ranked list of workflow recommendations from an ExecutionPlan.

    Each recommendation is linked to the plan via plan_id so the UI can
    use it to pass the right context when the user clicks "Prepare Workflow".
    """

    def generate(
        self,
        execution_plan: ExecutionPlan,
        readiness: WorkflowReadiness,
    ) -> list[WorkflowRecommendation]:
        """
        Return 1–3 WorkflowRecommendations ranked by priority.

        Args:
            execution_plan: the assembled plan from PlanBuilder
            readiness: readiness analysis (for state + score)
        """
        recommendations: list[WorkflowRecommendation] = []

        # 1. Primary recommendation — always present
        primary_action = _PRIMARY_ACTION.get(
            readiness.state, "Prepare workflow"
        )
        recommendations.append(
            WorkflowRecommendation(
                recommendation_id=str(uuid.uuid4())[:8],
                action=primary_action,
                readiness=readiness.state,
                confidence=execution_plan.confidence,
                approval_level=execution_plan.approval_level,
                plan_id=execution_plan.plan_id,
            )
        )

        # 2. Fill missing info (only when partially ready or blocked)
        if (
            readiness.state in (ReadinessState.partially_ready, ReadinessState.blocked)
            and execution_plan.missing_inputs
        ):
            missing_labels = ", ".join(
                m.replace("_", " ") for m in execution_plan.missing_inputs[:3]
            )
            recommendations.append(
                WorkflowRecommendation(
                    recommendation_id=str(uuid.uuid4())[:8],
                    action=f"Provide: {missing_labels}",
                    readiness=readiness.state,
                    confidence=0.9,
                    approval_level=ApprovalLevel.safe,
                    plan_id=execution_plan.plan_id,
                )
            )

        # 3. Research more (when confident but execution is complex)
        if (
            len(recommendations) < 3
            and readiness.readiness_score >= 0.5
            and execution_plan.approval_level in (
                ApprovalLevel.requires_approval,
                ApprovalLevel.high_risk,
            )
        ):
            recommendations.append(
                WorkflowRecommendation(
                    recommendation_id=str(uuid.uuid4())[:8],
                    action="Research more details first",
                    readiness=readiness.state,
                    confidence=0.7,
                    approval_level=ApprovalLevel.safe,
                    plan_id=execution_plan.plan_id,
                )
            )

        return recommendations[:3]


# Module-level singleton
engine = WorkflowRecommendationEngine()
