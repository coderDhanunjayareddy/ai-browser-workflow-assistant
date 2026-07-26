from __future__ import annotations

from typing import Any

from app.runtime_state_manager.entity_binding import register_entity, resolve_entity
from app.semantic_execution_kernel.entity_registry import find_entity
from app.semantic_execution_kernel.models import BrowserBinding, SemanticActionProposal, SemanticEntity


def proposal_from_planner_action(action: Any, entities: list[SemanticEntity], *, session_id: str | None = None) -> SemanticActionProposal | None:
    action_type = str(getattr(action, "action_type", "") or "").lower()
    value = str(getattr(action, "value", "") or "")
    selector = str(getattr(action, "target_selector", "") or "")
    description = str(getattr(action, "description", "") or "")
    unified = resolve_entity(
        session_id,
        entity_id=_strip_prefix(value, "entity:"),
        artifact_id=_strip_prefix(value, "artifact:"),
        canonical_url=value if value.startswith(("http://", "https://")) else None,
        runtime_resource_id=_strip_prefix(value, "runtime:"),
        selector_id=selector or _strip_prefix(value, "selector:"),
    ) if session_id else None
    entity = None
    if unified:
        entity = find_entity(entities, entity_id=unified.entity_id)
        if entity is None:
            entity = find_entity(entities, url=unified.canonical_url)
    if entity is None:
        entity = find_entity(
            entities,
            entity_id=_strip_prefix(value, "entity:"),
            artifact_id=_strip_prefix(value, "artifact:"),
            url=value if value.startswith(("http://", "https://")) else None,
            runtime_resource_id=_strip_prefix(value, "runtime:"),
            selector=selector or _strip_prefix(value, "selector:"),
        )
    if entity is None and session_id and action_type == "open_new_tab" and value.startswith(("http://", "https://")):
        unified = register_entity(
            session_id,
            entity_type="url_candidate",
            source_layer="semantic_execution_kernel",
            title=description or value,
            canonical_url=value,
            artifact_id=f"semantic_execution_kernel:url_candidate:{_stable_hash(value)}",
            confidence=0.72,
            source_page="planner_proposal",
            metadata={"source_action_type": action_type, "description": description[:240]},
        )
        entities.append(
            SemanticEntity(
                id=unified.entity_id,
                semantic_type=unified.entity_type,
                title=unified.title,
                url=unified.canonical_url,
                confidence=unified.confidence,
                source_page=unified.source_page or "",
                metadata=unified.metadata,
                browser_bindings=BrowserBinding(href=unified.canonical_url),
                artifact_id=unified.artifact_id,
                canonical_url=unified.canonical_url,
                runtime_resource_id=unified.runtime_resource_id,
                selector_ids=unified.selector_ids,
                source_layer=unified.source_layer,
                lifecycle_status="registered",
            )
        )
        entity = find_entity(entities, entity_id=unified.entity_id) or find_entity(entities, url=unified.canonical_url)

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


def _stable_hash(value: str) -> str:
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
