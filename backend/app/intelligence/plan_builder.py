"""
V4.0 Component 4 — ExecutionPlanBuilder.

Assembles the ExecutionPlan — the bridge object between research
findings and the Workflow Engine.

Combines:
  - ExecutionOpportunity  (what to do)
  - WorkflowReadiness     (what's available / missing)
  - GoalTree              (decomposed steps)
  - ApprovalLevel         (safety classification)
  - Research topic        (for naming)
"""
from __future__ import annotations

import uuid

from app.intelligence.models import (
    ActionType,
    ApprovalLevel,
    ExecutionOpportunity,
    ExecutionPlan,
    GoalTree,
    WorkflowReadiness,
    ReadinessState,
)

# Map ActionType → canonical workflow_type string consumed by WorkflowEngine
_WORKFLOW_TYPE_MAP: dict[ActionType, str] = {
    ActionType.book: "booking_workflow",
    ActionType.purchase: "purchase_workflow",
    ActionType.register: "registration_workflow",
    ActionType.schedule: "scheduling_workflow",
    ActionType.download: "download_workflow",
    ActionType.communicate: "communication_workflow",
    ActionType.navigate: "navigation_workflow",
    ActionType.rent: "rental_workflow",
    ActionType.apply: "application_workflow",
    ActionType.search: "search_workflow",
    ActionType.unknown: "generic_workflow",
}

# Recommended next action per readiness state
_NEXT_ACTION_TEMPLATES: dict[ReadinessState, str] = {
    ReadinessState.ready: "Prepare workflow with available context and launch.",
    ReadinessState.partially_ready: (
        "Provide missing information ({missing}) before launching."
    ),
    ReadinessState.blocked: (
        "Blocked: {reason}. Provide required details to proceed."
    ),
}


def _confidence_from_readiness(readiness: WorkflowReadiness) -> float:
    """Map readiness score and state to overall execution confidence."""
    base = readiness.readiness_score
    if readiness.state == ReadinessState.ready:
        return min(0.95, base)
    if readiness.state == ReadinessState.partially_ready:
        return min(0.6, base * 0.8)
    return min(0.3, base * 0.4)


def _extract_inferred_inputs(
    cognitive_session,
    required_inputs: list[str],
) -> dict[str, str]:
    """Pull values already known from the cognitive session."""
    if cognitive_session is None:
        return {}

    known: dict[str, str] = {}
    for entity in cognitive_session.active_entities.values():
        key = entity.name.lower().replace(" ", "_")
        value = entity.metadata.get("value") or entity.name
        if key in required_inputs:
            known[key] = value
        for alias in entity.aliases:
            alias_key = alias.lower().replace(" ", "_")
            if alias_key in required_inputs:
                known[alias_key] = value

    return known


class ExecutionPlanBuilder:
    """Assembles the ExecutionPlan from all upstream intelligence components."""

    def build(
        self,
        query: str,
        topic: str,
        opportunity: ExecutionOpportunity,
        readiness: WorkflowReadiness,
        approval_level: ApprovalLevel,
        goal_tree: GoalTree | None = None,
        cognitive_session=None,
    ) -> ExecutionPlan:
        """
        Build the ExecutionPlan.

        Args:
            query: original user message
            topic: research topic (from planner)
            opportunity: detected execution opportunity
            readiness: workflow readiness analysis
            approval_level: safety classification
            goal_tree: decomposed goal tree (optional)
            cognitive_session: for entity value inference
        """
        plan_id = str(uuid.uuid4())[:12]
        workflow_type = _WORKFLOW_TYPE_MAP.get(
            opportunity.action_type, "generic_workflow"
        )
        required_inputs = opportunity.required_entities
        inferred_inputs = _extract_inferred_inputs(cognitive_session, required_inputs)
        missing_inputs = [r for r in required_inputs if r not in inferred_inputs]

        confidence = _confidence_from_readiness(readiness)

        # Build recommended next action text
        if readiness.state == ReadinessState.ready:
            recommended_next_action = _NEXT_ACTION_TEMPLATES[ReadinessState.ready]
        elif readiness.state == ReadinessState.partially_ready:
            missing_label = ", ".join(
                m.replace("_", " ") for m in readiness.missing_entities
            )
            recommended_next_action = _NEXT_ACTION_TEMPLATES[
                ReadinessState.partially_ready
            ].format(missing=missing_label)
        else:
            reason = readiness.blocking_reason or "required information missing"
            recommended_next_action = _NEXT_ACTION_TEMPLATES[
                ReadinessState.blocked
            ].format(reason=reason)

        return ExecutionPlan(
            plan_id=plan_id,
            goal=query,
            workflow_type=workflow_type,
            required_inputs=required_inputs,
            inferred_inputs=inferred_inputs,
            missing_inputs=missing_inputs,
            confidence=round(confidence, 2),
            recommended_next_action=recommended_next_action,
            approval_level=approval_level,
            goal_tree=goal_tree,
        )


# Module-level singleton
builder = ExecutionPlanBuilder()
