"""
V4.0 Component 3 — WorkflowReadinessAnalyzer.

Determines whether a workflow can start immediately based on what
entities are already known in the cognitive session.

States:
  READY           — all required entities are available
  PARTIALLY_READY — some required entities are available
  BLOCKED         — critical required entities are entirely missing
"""
from __future__ import annotations

from app.intelligence.models import (
    ExecutionOpportunity,
    GoalTree,
    ReadinessState,
    WorkflowReadiness,
)

# These entities are considered "critical" — their absence alone causes BLOCKED
_CRITICAL_ENTITIES: dict[str, frozenset[str]] = {
    "book":      frozenset({"destination"}),
    "purchase":  frozenset({"product_name"}),
    "register":  frozenset({"email"}),
    "schedule":  frozenset({"date"}),
    "communicate": frozenset({"recipient"}),
    "download":  frozenset({"software_name"}),
    "rent":      frozenset({"location"}),
    "apply":     frozenset({"position"}),
}


def _extract_known_values(cognitive_session) -> dict[str, str]:
    """
    Extract entity name → value mapping from a CognitiveSession.
    Returns an empty dict if session is None.
    """
    if cognitive_session is None:
        return {}

    known: dict[str, str] = {}
    for entity in cognitive_session.active_entities.values():
        # Use lowercase name as key; value from metadata or entity name itself
        key = entity.name.lower().replace(" ", "_")
        value = entity.metadata.get("value") or entity.name
        known[key] = value
        # Also register aliases
        for alias in entity.aliases:
            known[alias.lower().replace(" ", "_")] = value

    # Also try active_goal text as a source of inferred info
    if cognitive_session.active_goal:
        known["goal_text"] = cognitive_session.active_goal.goal_text

    return known


class WorkflowReadinessAnalyzer:
    """
    Analyzes whether the cognitive session has enough entity context
    for a workflow to start without blocking on missing information.
    """

    def analyze(
        self,
        opportunity: ExecutionOpportunity,
        goal_tree: GoalTree | None,
        cognitive_session=None,
    ) -> WorkflowReadiness:
        """
        Compare required entities against what's available in cognitive session.

        Returns WorkflowReadiness with state, ready/missing entity lists,
        and a 0–1 readiness_score.
        """
        required = opportunity.required_entities
        if not required:
            # No requirements → always READY
            return WorkflowReadiness(
                state=ReadinessState.ready,
                ready_entities=[],
                missing_entities=[],
                blocking_reason=None,
                readiness_score=1.0,
            )

        known = _extract_known_values(cognitive_session)
        ready: list[str] = []
        missing: list[str] = []

        for req in required:
            if req in known:
                ready.append(req)
            else:
                missing.append(req)

        readiness_score = len(ready) / len(required) if required else 1.0

        # Determine critical entities for this action type
        critical = _CRITICAL_ENTITIES.get(opportunity.action_type.value, frozenset())
        critical_missing = [m for m in missing if m in critical]

        if not missing:
            state = ReadinessState.ready
            blocking_reason = None
        elif critical_missing:
            state = ReadinessState.blocked
            labels = ", ".join(m.replace("_", " ") for m in critical_missing)
            blocking_reason = f"Missing critical information: {labels}"
        else:
            state = ReadinessState.partially_ready
            blocking_reason = None

        return WorkflowReadiness(
            state=state,
            ready_entities=ready,
            missing_entities=missing,
            blocking_reason=blocking_reason,
            readiness_score=round(readiness_score, 2),
        )


# Module-level singleton
analyzer = WorkflowReadinessAnalyzer()
