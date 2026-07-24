from __future__ import annotations

from app.semantic_execution_kernel.entity_registry import find_entity
from app.semantic_execution_kernel.models import EligibilityResult, MissionState, SemanticActionProposal, SemanticEntity


def check_eligibility(
    proposal: SemanticActionProposal | None,
    *,
    mission_state: MissionState,
    entities: list[SemanticEntity],
    loop_status: dict,
) -> EligibilityResult:
    if proposal is None:
        return EligibilityResult(False, "no semantic proposal", ["missing_proposal"], 0)
    failures: list[str] = []
    entity = find_entity(entities, entity_id=proposal.entity_id) if proposal.entity_id else None
    retry_count = _retry_count(mission_state)

    if mission_state.blocked:
        failures.append("mission_blocked")
    if loop_status.get("detected"):
        failures.append("loop_detected")
    if proposal.action_type in {"OPEN_ENTITY", "CLICK_ENTITY", "FILL_FORM", "UPLOAD_FILE", "DOWNLOAD_FILE", "SKIP_ENTITY"} and entity is None:
        failures.append("entity_missing")
    if entity is not None and proposal.action_type in {"OPEN_ENTITY", "DOWNLOAD_FILE"} and not entity.url and not entity.browser_bindings.selector:
        failures.append("entity_has_no_url_or_selector")
    if entity is not None and proposal.action_type in {"CLICK_ENTITY", "FILL_FORM", "UPLOAD_FILE"} and not entity.browser_bindings.selector:
        failures.append("selector_binding_missing")
    if retry_count >= 3:
        failures.append("retry_budget_exceeded")

    return EligibilityResult(
        eligible=not failures,
        reason="eligible" if not failures else ", ".join(failures),
        failures=failures,
        retry_count=retry_count,
    )


def _retry_count(mission_state: MissionState) -> int:
    for goal in mission_state.goals:
        if goal.id == mission_state.current_goal_id:
            return goal.retries
    return 0
