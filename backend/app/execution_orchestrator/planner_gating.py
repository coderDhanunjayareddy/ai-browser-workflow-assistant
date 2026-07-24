from __future__ import annotations

from app.execution_orchestrator.models import ExecutionOrchestratorSnapshot, PhaseState
from app.schemas.response import AnalyzeResponse, ReplanOutcome


def planner_constraints(snapshot: ExecutionOrchestratorSnapshot) -> dict[str, object]:
    phase = snapshot.active_phase
    return {
        "current_phase": phase.name,
        "phase_objective": phase.objective,
        "allowed_actions": phase.allowed_actions,
        "forbidden_actions": phase.forbidden_actions,
        "phase_rule": "Planner must work only inside the active phase. Do not restart completed phases.",
    }


def action_allowed(action_type: str, phase: PhaseState) -> bool:
    normalized = (action_type or "").lower()
    if normalized in phase.forbidden_actions:
        return False
    if phase.allowed_actions and normalized not in phase.allowed_actions:
        return False
    return True


def reject_for_phase(result: AnalyzeResponse, snapshot: ExecutionOrchestratorSnapshot, reason: str) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nV4.8 Execution Orchestrator rejected this planner action "
            f"because it violates the active phase."
        ),
        outcome_kind="replan",
        clarification_question=None,
        report=None,
        replan=ReplanOutcome(
            reason=(
                f"{reason}. Current phase: {snapshot.active_phase.name}. "
                f"Objective: {snapshot.active_phase.objective}. "
                f"Allowed actions: {', '.join(snapshot.active_phase.allowed_actions)}."
            )
        ),
        suggested_actions=[],
    )
