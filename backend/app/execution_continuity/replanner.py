from __future__ import annotations

from app.execution_continuity.models import ContinuitySnapshot
from app.schemas.response import AnalyzeResponse, ReplanOutcome


def apply_continuity_replanner(result: AnalyzeResponse, snapshot: ContinuitySnapshot) -> AnalyzeResponse:
    validation = snapshot.progress_validation
    if validation.recommendation != "replan":
        return result
    if not result.suggested_actions:
        return result
    proposed = result.suggested_actions[0]
    if not _proposed_repeats_history(proposed, snapshot):
        return result
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nV4.7 Execution Continuity blocked a repeated browser action. "
            f"Current objective remains: {snapshot.mission.current_objective}."
        ),
        outcome_kind="replan",
        clarification_question=None,
        report=None,
        replan=ReplanOutcome(
            reason=(
                f"{validation.reason}. Continue from completed work instead of restarting. "
                f"Next objective: {snapshot.mission.current_objective}."
            )
        ),
        suggested_actions=[],
    )


def _proposed_repeats_history(action: object, snapshot: ContinuitySnapshot) -> bool:
    action_type = str(getattr(action, "action_type", "") or "").lower()
    target = str(getattr(action, "target_selector", "") or getattr(action, "description", "") or "").lower()
    value = str(getattr(action, "value", "") or "").lower().rstrip("/")
    for record in snapshot.recent_actions[-4:]:
        if action_type != record.action_type:
            continue
        record_target = (record.target or "").lower()
        record_value = (record.value or "").lower().rstrip("/")
        if target and target == record_target:
            return True
        if value and value == record_value:
            return True
        if not target and not value:
            return True
    return False
