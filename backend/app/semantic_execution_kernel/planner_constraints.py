from __future__ import annotations

import json
from typing import Any

from app.runtime_state_manager.entity_binding import resolve_entity
from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer
from app.semantic_execution_kernel.entity_registry import find_entity
from app.semantic_execution_kernel.models import SemanticActionProposal, SemanticEntity


def proposal_from_planner_action(action: Any, entities: list[SemanticEntity], *, session_id: str | None = None) -> SemanticActionProposal | None:
    action_type = str(getattr(action, "action_type", "") or "").lower()
    value = str(getattr(action, "value", "") or "")
    selector = str(getattr(action, "target_selector", "") or "")
    description = str(getattr(action, "description", "") or "")
    lookup_keys = {
        "entity_id": _strip_prefix(value, "entity:"),
        "artifact_id": _strip_prefix(value, "artifact:"),
        "canonical_url": value if value.startswith(("http://", "https://")) else None,
        "runtime_resource_id": _strip_prefix(value, "runtime:"),
        "selector_id": selector or _strip_prefix(value, "selector:"),
    }
    _debug_v494_proposal(
        "PLANNER_RESPONSE_RECEIVED",
        session_id=session_id,
        payload={
            "source_action_type": action_type,
            "value": value,
            "selector": selector,
            "description": description,
            "derived_lookup_keys": lookup_keys,
            "semantic_entity_count": len(entities),
        },
    )
    unified = resolve_entity(
        session_id,
        entity_id=lookup_keys["entity_id"],
        artifact_id=lookup_keys["artifact_id"],
        canonical_url=lookup_keys["canonical_url"],
        runtime_resource_id=lookup_keys["runtime_resource_id"],
        selector_id=lookup_keys["selector_id"],
    ) if session_id else None
    _debug_v494_proposal(
        "RUNTIME_REGISTRY_RESOLVE_RETURNED",
        session_id=session_id,
        payload={
            "unified_found": unified is not None,
            "matched_entity_id": unified.entity_id if unified else None,
            "matched_canonical_url": unified.canonical_url if unified else None,
            "matched_artifact_id": unified.artifact_id if unified else None,
            "matched_selector_id": unified.selector_ids[0] if unified and unified.selector_ids else None,
            "matched_runtime_resource_id": unified.runtime_resource_id if unified else None,
        },
    )
    entity = None
    if unified:
        entity = find_entity(entities, entity_id=unified.entity_id)
        _debug_v494_proposal(
            "KERNEL_ENTITY_FIND_BY_UNIFIED_ID",
            session_id=session_id,
            payload={
                "requested_entity_id": unified.entity_id,
                "found": entity is not None,
                "matched_entity_id": entity.id if entity else None,
                "matched_canonical_url": (entity.canonical_url or entity.url) if entity else None,
            },
        )
        if entity is None:
            entity = find_entity(entities, url=unified.canonical_url)
            _debug_v494_proposal(
                "KERNEL_ENTITY_FIND_BY_UNIFIED_URL",
                session_id=session_id,
                payload={
                    "requested_url": unified.canonical_url,
                    "found": entity is not None,
                    "matched_entity_id": entity.id if entity else None,
                    "matched_canonical_url": (entity.canonical_url or entity.url) if entity else None,
                },
            )
    if entity is None:
        entity = find_entity(
            entities,
            entity_id=lookup_keys["entity_id"],
            artifact_id=lookup_keys["artifact_id"],
            url=lookup_keys["canonical_url"],
            runtime_resource_id=lookup_keys["runtime_resource_id"],
            selector=lookup_keys["selector_id"],
        )
        _debug_v494_proposal(
            "KERNEL_ENTITY_FIND_BY_PLANNER_KEYS",
            session_id=session_id,
            payload={
                "requested": lookup_keys,
                "found": entity is not None,
                "matched_entity_id": entity.id if entity else None,
                "matched_canonical_url": (entity.canonical_url or entity.url) if entity else None,
            },
        )
    if entity is None and session_id and action_type == "open_new_tab" and value.startswith(("http://", "https://")):
        _debug_v494_proposal(
            "ENTITY_LOOKUP_FAILED_BRANCH",
            session_id=session_id,
            payload={
                "branch_reason": "entity is None and action_type=open_new_tab and value is URL",
                "value": value,
                "semantic_entity_count": len(entities),
            },
        )
        get_entity_pipeline_tracer().verify_exists(
            session_id,
            stage="SEMANTIC_KERNEL",
            reason="SemanticKernel entity lookup failed for planner URL proposal; kernel-side entity creation is forbidden",
            exists=False,
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
    _debug_v494_proposal(
        "PROPOSAL_NORMALIZED",
        session_id=session_id,
        payload={
            "source_action_type": action_type,
            "semantic_action_type": semantic_type,
            "entity_found": entity is not None,
            "proposal_entity_id": entity.id if entity else None,
            "proposal_canonical_url": (entity.canonical_url or entity.url) if entity else None,
            "normalization_branch": f"{action_type}-> {semantic_type}",
        },
    )

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
            "session_id": session_id or "",
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


def _debug_v494_proposal(event: str, *, session_id: str | None, payload: dict[str, Any]) -> None:
    try:
        print(
            "[V4.9.4 kernel-lookup] PLANNER_PROPOSAL "
            + json.dumps(
                {
                    "event": event,
                    "mission_id": session_id,
                    **payload,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception as exc:
        print(f"[V4.9.4 kernel-lookup] PLANNER_PROPOSAL_LOG_FAILED {exc}", flush=True)
