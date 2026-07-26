from __future__ import annotations

import json

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
        _debug_v494_eligibility("NO_PROPOSAL", {"reason": "proposal is None"})
        return EligibilityResult(False, "no semantic proposal", ["missing_proposal"], 0)
    failures: list[str] = []
    entity = find_entity(entities, entity_id=proposal.entity_id) if proposal.entity_id else None
    retry_count = _retry_count(mission_state)
    _debug_v494_eligibility(
        "START",
        {
            "proposal_action_type": proposal.action_type,
            "proposal_entity_id": proposal.entity_id,
            "proposal_parameters": proposal.parameters,
            "entity_lookup_output": "hit" if entity else "miss",
            "matched_entity_id": entity.id if entity else None,
            "matched_canonical_url": (entity.canonical_url or entity.url) if entity else None,
            "semantic_entity_count": len(entities),
            "mission_blocked": mission_state.blocked,
            "loop_detected": bool(loop_status.get("detected")),
            "retry_count": retry_count,
        },
    )

    if mission_state.blocked:
        failures.append("mission_blocked")
        _debug_v494_eligibility("BRANCH_MISSION_BLOCKED", {"condition": "mission_state.blocked is true"})
    if loop_status.get("detected"):
        failures.append("loop_detected")
        _debug_v494_eligibility("BRANCH_LOOP_DETECTED", {"condition": "loop_status.detected is true", "loop_status": loop_status})
    if proposal.action_type in {"OPEN_ENTITY", "CLICK_ENTITY", "FILL_FORM", "UPLOAD_FILE", "DOWNLOAD_FILE", "SKIP_ENTITY"} and entity is None:
        failures.append("entity_missing")
        _debug_v494_eligibility(
            "BRANCH_ENTITY_MISSING",
            {
                "condition": "proposal requires entity and entity lookup output is miss",
                "proposal_action_type": proposal.action_type,
                "proposal_entity_id": proposal.entity_id,
                "failure_reason": "entity_missing",
            },
        )
    if entity is not None and proposal.action_type in {"OPEN_ENTITY", "DOWNLOAD_FILE"} and not entity.url and not entity.browser_bindings.selector:
        failures.append("entity_has_no_url_or_selector")
        _debug_v494_eligibility("BRANCH_ENTITY_HAS_NO_URL_OR_SELECTOR", {"entity_id": entity.id, "url": entity.url, "selector": entity.browser_bindings.selector})
    if entity is not None and proposal.action_type in {"CLICK_ENTITY", "FILL_FORM", "UPLOAD_FILE"} and not entity.browser_bindings.selector:
        failures.append("selector_binding_missing")
        _debug_v494_eligibility("BRANCH_SELECTOR_BINDING_MISSING", {"entity_id": entity.id, "selector": entity.browser_bindings.selector})
    if retry_count >= 3:
        failures.append("retry_budget_exceeded")
        _debug_v494_eligibility("BRANCH_RETRY_BUDGET_EXCEEDED", {"retry_count": retry_count})

    result = EligibilityResult(
        eligible=not failures,
        reason="eligible" if not failures else ", ".join(failures),
        failures=failures,
        retry_count=retry_count,
    )
    _debug_v494_eligibility("RESULT", result.to_dict())
    return result


def _retry_count(mission_state: MissionState) -> int:
    for goal in mission_state.goals:
        if goal.id == mission_state.current_goal_id:
            return goal.retries
    return 0


def _debug_v494_eligibility(event: str, payload: dict) -> None:
    try:
        print(
            "[V4.9.4 kernel-lookup] ELIGIBILITY "
            + json.dumps({"event": event, **payload}, ensure_ascii=False),
            flush=True,
        )
    except Exception as exc:
        print(f"[V4.9.4 kernel-lookup] ELIGIBILITY_LOG_FAILED {exc}", flush=True)
