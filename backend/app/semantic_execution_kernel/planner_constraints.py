from __future__ import annotations

import json
from typing import Any

from app.diagnostics.console import diagnostic_terminal_enabled, safe_print
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


def legal_action_prompt(entities: list[SemanticEntity]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if any(entity.url for entity in entities):
        actions.append(_semantic_intent("OPEN_ENTITY", "URL-backed entities are available", "execution_orchestrator"))
    if any(entity.semantic_type in {"button", "link"} for entity in entities):
        actions.append(_semantic_intent("CLICK_ENTITY", "clickable button or link entities are available", "browser_control"))
    if any(entity.semantic_type == "form" for entity in entities):
        actions.append(_semantic_intent("FILL_FORM", "form entities are available", "browser_control"))
    actions.extend([
        _semantic_intent("READ_PAGE", "current page can be read", "knowledge_extraction"),
        _semantic_intent("EXTRACT_FIELDS", "visible content can be structured", "knowledge_extraction"),
        _semantic_intent("WAIT_FOR_STATE", "bounded wait is always legal when state is changing", "execution_orchestrator"),
        _semantic_intent("MARK_COMPLETE", "allowed only with evidence", "mission_completion"),
    ])
    return actions[:12]


def _semantic_intent(action: str, reason: str, owner: str) -> dict[str, Any]:
    return {
        "action": action,
        "intent": action.lower(),
        "owner": owner,
        "browser_executable": owner == "browser_control",
        "reason": reason,
    }


def _strip_prefix(value: str, prefix: str) -> str | None:
    return value[len(prefix):] if value.startswith(prefix) and len(value) > len(prefix) else None


def _debug_v494_proposal(event: str, *, session_id: str | None, payload: dict[str, Any]) -> None:
    if not diagnostic_terminal_enabled("AI_BROWSER_KERNEL_LOOKUP_TRACE"):
        return
    try:
        safe_print(
            "[V4.9.4 kernel-lookup] PLANNER_PROPOSAL "
            + json.dumps(
                {
                    "event": event,
                    "mission_id": session_id,
                    **payload,
                },
                ensure_ascii=True,
            )
        )
    except Exception as exc:
        safe_print(f"[V4.9.4 kernel-lookup] PLANNER_PROPOSAL_LOG_FAILED {exc}")
