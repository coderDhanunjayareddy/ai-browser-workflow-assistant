from __future__ import annotations

from app.semantic_execution_kernel.entity_registry import find_entity
from app.semantic_execution_kernel.models import EligibilityResult, GroundingResult, SemanticActionProposal, SemanticEntity
from app.schemas.response import SuggestedAction


def ground_semantic_action(
    proposal: SemanticActionProposal | None,
    *,
    entities: list[SemanticEntity],
    eligibility: EligibilityResult,
) -> GroundingResult:
    if proposal is None:
        return GroundingResult(False, None, None, None, "no proposal")
    if not eligibility.eligible:
        return GroundingResult(False, None, None, None, eligibility.reason)
    entity = find_entity(entities, entity_id=proposal.entity_id) if proposal.entity_id else None

    if proposal.action_type == "OPEN_ENTITY":
        value = entity.url if entity and entity.url else proposal.parameters.get("value")
        return GroundingResult(bool(value), "open_new_tab", "", value or None, "entity URL resolved")
    if proposal.action_type == "FOCUS_TAB":
        value = proposal.parameters.get("value")
        return GroundingResult(bool(value), "focus_existing_tab", "", value or None, "tab reference resolved")
    if proposal.action_type == "CLICK_ENTITY":
        selector = entity.browser_bindings.selector if entity else proposal.parameters.get("selector")
        return GroundingResult(bool(selector), "click", selector or None, None, "entity selector resolved")
    if proposal.action_type == "FILL_FORM":
        selector = entity.browser_bindings.selector if entity else proposal.parameters.get("selector")
        return GroundingResult(bool(selector), "fill", selector or None, proposal.parameters.get("value") or None, "form binding resolved")
    if proposal.action_type == "WAIT_FOR_STATE":
        return GroundingResult(True, "wait", "window", proposal.parameters.get("value") or "1000", "bounded wait")
    if proposal.action_type == "COLLECT_RESULTS":
        return GroundingResult(True, "scroll", "window", proposal.parameters.get("value") or "down", "collect more visible entities")
    return GroundingResult(False, None, None, None, f"{proposal.action_type} is planner-context only")


def apply_grounding_to_action(action: SuggestedAction, grounding: GroundingResult) -> SuggestedAction:
    if not grounding.grounded or not grounding.action_type:
        return action
    action.action_type = grounding.action_type  # type: ignore[assignment]
    action.target_selector = grounding.target_selector or ""
    action.value = grounding.value
    action.reasoning = f"Semantic Execution Kernel grounded this action: {grounding.reason}."
    return action
