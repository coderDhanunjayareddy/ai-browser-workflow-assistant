"""
V4.0 Component 6 — WorkflowBootstrapGenerator.

Converts research findings + entities + goal tree into BootstrapFacts —
a rich initialization context for the Workflow Engine that is far more
detailed than the existing WorkflowHandoffPayload.

The Workflow Engine can consume BootstrapFacts to:
  - Pre-fill form fields from inferred entity values
  - Start at the right workflow step (skipping steps already resolved)
  - Apply the correct approval policy before the first action
"""
from __future__ import annotations

from app.intelligence.models import (
    ApprovalLevel,
    BootstrapFacts,
    ExecutionPlan,
    GoalTree,
)


def _flatten_leaf_goals(goal_tree: GoalTree | None) -> list[str]:
    """Return the text of all leaf nodes in BFS order."""
    if goal_tree is None:
        return []
    return [n.text for n in goal_tree.get_leaves()]


class WorkflowBootstrapGenerator:
    """
    Generates BootstrapFacts from the assembled intelligence result.

    BootstrapFacts replace the simpler WorkflowHandoffPayload when the
    intelligence layer has run successfully.
    """

    def generate(
        self,
        query: str,
        execution_plan: ExecutionPlan,
        research_topic: str,
        research_summary: str,
        cognitive_session=None,
    ) -> BootstrapFacts:
        """
        Build BootstrapFacts.

        Args:
            query: original user message
            execution_plan: assembled execution plan
            research_topic: topic from research session
            research_summary: executive summary from research report
            cognitive_session: for goal text and additional entity values
        """
        goal_text: str | None = None
        if cognitive_session is not None and cognitive_session.active_goal:
            goal_text = cognitive_session.active_goal.goal_text

        # Merge inferred inputs from plan with any extra entities from session
        pre_filled: dict[str, str] = dict(execution_plan.inferred_inputs)
        if cognitive_session is not None:
            for entity in cognitive_session.active_entities.values():
                key = entity.name.lower().replace(" ", "_")
                if key not in pre_filled:
                    value = entity.metadata.get("value") or entity.name
                    pre_filled[key] = value

        leaf_goals = _flatten_leaf_goals(execution_plan.goal_tree)

        return BootstrapFacts(
            query=query,
            goal_text=goal_text,
            workflow_type=execution_plan.workflow_type,
            goal_tree_summary=leaf_goals,
            pre_filled_entities=pre_filled,
            research_topic=research_topic,
            research_summary=research_summary[:500] if research_summary else "",
            confidence=execution_plan.confidence,
            approval_level=execution_plan.approval_level,
        )


# Module-level singleton
generator = WorkflowBootstrapGenerator()
