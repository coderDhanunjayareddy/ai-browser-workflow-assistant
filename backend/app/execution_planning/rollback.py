"""
V9.0 Execution Planning Layer — RollbackPlanner.

Generates rollback METADATA only. It never executes a rollback — it only
describes what a rollback WOULD be for each step, so the future Execution Gateway
can undo a mutating action if it fails.

Pure deterministic mapping. No browser code.
"""
from __future__ import annotations

from typing import Any

from app.execution_planning.models import (
    ACTION_PROFILE,
    ActionType,
    ExecutionStep,
    RollbackAction,
)


class RollbackPlanner:

    def rollback_for_action(self, action_type: ActionType) -> RollbackAction:
        """Canonical rollback action for a given action type."""
        return ACTION_PROFILE[action_type]["rollback"]

    def describe(self, step: ExecutionStep) -> dict[str, Any]:
        """Rollback descriptor for a single step (metadata only)."""
        ra = step.rollback_action
        return {
            "step_id":         step.step_id,
            "order":           step.order,
            "action_type":     step.action_type.value,
            "rollback_action": ra.value,
            "reversible":      ra != RollbackAction.none,
            "requires_manual": ra == RollbackAction.manual_review,
            "target":          step.target_description,
        }

    def plan_rollback(self, steps: list[ExecutionStep]) -> dict[str, Any]:
        """
        Build the rollback metadata for an entire plan.

        Rollback steps are listed in REVERSE order (last action undone first),
        as a future gateway would unwind them. No execution occurs here.
        """
        reversed_steps = sorted(steps, key=lambda s: s.order, reverse=True)
        descriptors = [self.describe(s) for s in reversed_steps]

        mutating = [s for s in steps if s.is_mutating]
        covered  = [s for s in mutating if s.has_rollback]

        return {
            "rollback_steps":      descriptors,
            "mutating_steps":      len(mutating),
            "covered_steps":       len(covered),
            "fully_supported":     len(mutating) == len(covered),
            "manual_steps":        sum(1 for d in descriptors if d["requires_manual"]),
        }

    def is_supported(self, steps: list[ExecutionStep]) -> bool:
        """True iff every mutating step has a defined rollback action."""
        for s in steps:
            if s.requires_rollback and not s.has_rollback:
                return False
        return True


# ── Module-level singleton ────────────────────────────────────────────────────

_planner = RollbackPlanner()


def rollback_for_action(action_type: ActionType) -> RollbackAction:
    return _planner.rollback_for_action(action_type)

def describe(step: ExecutionStep) -> dict:
    return _planner.describe(step)

def plan_rollback(steps: list[ExecutionStep]) -> dict:
    return _planner.plan_rollback(steps)

def is_supported(steps: list[ExecutionStep]) -> bool:
    return _planner.is_supported(steps)
