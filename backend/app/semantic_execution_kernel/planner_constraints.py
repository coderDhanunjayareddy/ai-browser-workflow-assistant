from __future__ import annotations

from typing import Any

from app.semantic_execution_kernel.entity_registry import find_entity
from app.semantic_execution_kernel.models import SemanticActionProposal, SemanticEntity


def proposal_from_planner_action(action: Any, entities: list[SemanticEntity]) -> SemanticActionProposal | None:
    action_type = str(getattr(action, "action_type", "") or "").lower()
    value = str(getattr(action, "value", "") or "")
    selector = str(getattr(action, "target_selector", "") or "")
    description = str(getattr(action, "description", "") or "")
    entity = find_entity(
        entities,
        entity_id=_strip_prefix(value, "entity:"),
        artifact_id=_strip_prefix(value, "artifact:"),
        url=value if value.startswith(("http://", "https://")) else None,
        runtime_resource_id=_strip_prefix(value, "runtime:"),
        selector=selector or _strip_prefix(value, "selector:"),
    )

    if action_type == "navigate":
        semantic_type = "SEARCH_WEB" if value.startswith(("http://", "https://")) else "WAIT_FOR_STATE"
    elif action_type == "open_new_tab":
        semantic_type = "OPEN_ENTITY"
    elif action_type in {"switch_tab", "focus_existing_tab"}:
        semantic_type = "FOCUS_TAB"
    elif action_type == "fill":
        semantic_type = "FILL_FORM"
    elif action_type == "click":
        semantic_type = "CLICK_ENTITY"
    elif action_type == "wait":
        semantic_type = "WAIT_FOR_STATE"
    elif action_type == "scroll":
        semantic_type = "COLLECT_RESULTS"
    else:
        semantic_type = "CLICK_ENTITY"

    return SemanticActionProposal(
        action_type=semantic_type,  # type: ignore[arg-type]
        entity_id=entity.id if entity else None,
        parameters={
            "value": value,
            "selector": selector,
            "description": description,
            "artifact_id": entity.artifact_id if entity else "",
            "canonical_url": (entity.canonical_url or entity.url) if entity else "",
            "runtime_resource_id": entity.runtime_resource_id if entity else "",
        },
        source_action_type=action_type,
        source_description=description,
    )


def legal_action_prompt(entities: list[SemanticEntity]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if any(entity.url for entity in entities):
        actions.append({"action": "OPEN_ENTITY", "reason": "URL-backed entities are available"})
    if any(entity.semantic_type == "button" for entity in entities):
        actions.append({"action": "CLICK_ENTITY", "reason": "button entities are available"})
    if any(entity.semantic_type == "form" for entity in entities):
        actions.append({"action": "FILL_FORM", "reason": "form entities are available"})
    actions.extend([
        {"action": "READ_PAGE", "reason": "current page can be read"},
        {"action": "EXTRACT_FIELDS", "reason": "visible content can be structured"},
        {"action": "WAIT_FOR_STATE", "reason": "bounded wait is always legal when state is changing"},
        {"action": "MARK_COMPLETE", "reason": "allowed only with evidence"},
    ])
    return actions[:12]


def _strip_prefix(value: str, prefix: str) -> str | None:
    return value[len(prefix):] if value.startswith(prefix) and len(value) > len(prefix) else None
