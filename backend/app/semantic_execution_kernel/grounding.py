from __future__ import annotations

import json

from app.diagnostics.console import diagnostic_terminal_enabled, safe_print
from app.runtime_state_manager.browser_action_reference import (
    exposes_backend_logical_tab,
    to_browser_tab_reference,
)
from app.semantic_execution_kernel.entity_registry import find_entity
from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer
from app.semantic_execution_kernel.models import EligibilityResult, GroundingResult, SemanticActionProposal, SemanticEntity
from app.schemas.response import SuggestedAction


def ground_semantic_action(
    proposal: SemanticActionProposal | None,
    *,
    entities: list[SemanticEntity],
    eligibility: EligibilityResult,
) -> GroundingResult:
    if proposal is None:
        _debug_v494_grounding("NO_PROPOSAL", {"reason": "proposal is None"})
        return GroundingResult(False, None, None, None, "no proposal")
    if not eligibility.eligible:
        _debug_v494_grounding("INELIGIBLE_BRANCH", {"reason": eligibility.reason, "failures": eligibility.failures})
        return GroundingResult(False, None, None, None, eligibility.reason)
    entity = find_entity(entities, entity_id=proposal.entity_id) if proposal.entity_id else None
    mission_id = str(proposal.parameters.get("session_id") or "")
    _debug_v494_grounding(
        "START",
        {
            "mission_id": mission_id,
            "proposal_action_type": proposal.action_type,
            "proposal_entity_id": proposal.entity_id,
            "entity_lookup_output": "hit" if entity else "miss",
            "matched_entity_id": entity.id if entity else None,
            "matched_canonical_url": (entity.canonical_url or entity.url) if entity else None,
            "semantic_entity_count": len(entities),
        },
    )
    if mission_id:
        get_entity_pipeline_tracer().verify_exists(
            mission_id,
            stage="GROUNDING",
            reason="Kernel -> Grounding resolved_entity exists",
            exists=entity is not None or proposal.action_type in {"WAIT_FOR_STATE", "COLLECT_RESULTS", "FOCUS_TAB"},
            trace_id=entity.trace_id if entity else None,
            entity_id=proposal.entity_id,
        )

    if proposal.action_type == "OPEN_ENTITY":
        value = entity.url if entity and entity.url else proposal.parameters.get("value")
        result = GroundingResult(bool(value), "open_new_tab", "", value or None, "entity URL resolved")
        _debug_v494_grounding("BRANCH_OPEN_ENTITY", {"value_source": "entity.url" if entity and entity.url else "proposal.parameters.value", "result": result.to_dict()})
        return result
    if proposal.action_type == "FOCUS_TAB":
        value = proposal.parameters.get("value")
        browser_reference = to_browser_tab_reference(mission_id, value)
        grounded = bool(browser_reference) and not exposes_backend_logical_tab(browser_reference)
        result = GroundingResult(
            grounded,
            "focus_existing_tab" if grounded else None,
            "",
            browser_reference if grounded else None,
            "tab reference resolved" if grounded else "logical tab reference unresolved",
        )
        _debug_v494_grounding(
            "BRANCH_FOCUS_TAB",
            {
                "input_value": value,
                "browser_reference": browser_reference,
                "exposed_backend_logical_tab": exposes_backend_logical_tab(browser_reference),
                "result": result.to_dict(),
            },
        )
        return result
    if proposal.action_type == "CLICK_ENTITY":
        selector = entity.browser_bindings.selector if entity else proposal.parameters.get("selector")
        result = GroundingResult(bool(selector), "click", selector or None, None, "entity selector resolved")
        _debug_v494_grounding("BRANCH_CLICK_ENTITY", {"selector_source": "entity.browser_bindings.selector" if entity else "proposal.parameters.selector", "result": result.to_dict()})
        return result
    if proposal.action_type == "FILL_FORM":
        selector = entity.browser_bindings.selector if entity else proposal.parameters.get("selector")
        result = GroundingResult(bool(selector), "fill", selector or None, proposal.parameters.get("value") or None, "form binding resolved")
        _debug_v494_grounding("BRANCH_FILL_FORM", {"selector_source": "entity.browser_bindings.selector" if entity else "proposal.parameters.selector", "result": result.to_dict()})
        return result
    if proposal.action_type == "WAIT_FOR_STATE":
        result = GroundingResult(True, "wait", "window", proposal.parameters.get("value") or "1000", "bounded wait")
        _debug_v494_grounding("BRANCH_WAIT_FOR_STATE", {"result": result.to_dict()})
        return result
    if proposal.action_type == "COLLECT_RESULTS":
        result = GroundingResult(True, "scroll", "window", proposal.parameters.get("value") or "down", "collect more visible entities")
        _debug_v494_grounding("BRANCH_COLLECT_RESULTS", {"result": result.to_dict()})
        return result
    result = GroundingResult(False, None, None, None, f"{proposal.action_type} is planner-context only")
    _debug_v494_grounding("BRANCH_PLANNER_CONTEXT_ONLY", {"result": result.to_dict()})
    return result


def apply_grounding_to_action(action: SuggestedAction, grounding: GroundingResult) -> SuggestedAction:
    if not grounding.grounded or not grounding.action_type:
        return action
    action.action_type = grounding.action_type  # type: ignore[assignment]
    action.target_selector = grounding.target_selector or ""
    action.value = grounding.value
    action.reasoning = f"Semantic Execution Kernel grounded this action: {grounding.reason}."
    return action


def _debug_v494_grounding(event: str, payload: dict) -> None:
    if not diagnostic_terminal_enabled("AI_BROWSER_KERNEL_LOOKUP_TRACE"):
        return
    try:
        safe_print(
            "[V4.9.4 kernel-lookup] GROUNDING "
            + json.dumps({"event": event, **payload}, ensure_ascii=True)
        )
    except Exception as exc:
        safe_print(f"[V4.9.4 kernel-lookup] GROUNDING_LOG_FAILED {exc}")
