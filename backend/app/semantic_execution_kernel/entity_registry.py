from __future__ import annotations

import hashlib
import json
from typing import Any

from app.runtime_state_manager.entity_binding import list_entities, register_entity
from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer
from app.semantic_execution_kernel.models import BrowserBinding, SemanticEntity


def build_entity_registry(page_context: Any, *, session_id: str | None = None) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    source_page = str(getattr(page_context, "url", "") or "")
    tracer = get_entity_pipeline_tracer()
    extracted_count = 0
    for element in list(getattr(page_context, "interactive_elements", []) or [])[:120]:
        data = element.model_dump() if hasattr(element, "model_dump") else dict(element)
        entity = _entity_from_element(data, source_page)
        if entity is None:
            continue
        extracted_count += 1
        tracer.emit(session_id or "default", "ENTITY_EXTRACTION", success=True, reason="page_context interactive element extracted", entity_id=entity.id, artifact_id=entity.artifact_id, canonical_url=entity.canonical_url, selector_id=entity.selector_ids[0] if entity.selector_ids else None, source=entity.source_layer)
        if session_id:
            _register_if_scoped(session_id, entity)
        else:
            entities.append(entity)
    for block in list(getattr(page_context, "content_blocks", []) or [])[:60]:
        data = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        entity = _entity_from_block(data, source_page)
        if entity is None:
            continue
        extracted_count += 1
        tracer.emit(session_id or "default", "ENTITY_EXTRACTION", success=True, reason="page_context content block extracted", entity_id=entity.id, artifact_id=entity.artifact_id, canonical_url=entity.canonical_url, selector_id=entity.selector_ids[0] if entity.selector_ids else None, source=entity.source_layer)
        if session_id:
            _register_if_scoped(session_id, entity)
        else:
            entities.append(entity)
    if session_id:
        unified_entities = list_entities(session_id)
        entities = [_from_unified_entity(entity) for entity in unified_entities]
        tracer.verify_count(
            session_id,
            stage="SEMANTIC_KERNEL",
            reason="EntityRegistry -> SemanticKernel kernel_received >= registered_entities",
            expected=len(unified_entities),
            actual=len(entities),
            comparator="gte",
        )
    deduped = entities if session_id else _dedupe_entities(entities)
    if session_id:
        tracer.emit(session_id, "SEMANTIC_KERNEL", success=True, reason="received", count=len(deduped))
        for entity in deduped:
            tracer.emit(session_id, "SEMANTIC_KERNEL", success=True, reason="received", trace_id=entity.trace_id, entity_id=entity.id, artifact_id=entity.artifact_id, canonical_url=entity.canonical_url or entity.url, selector_id=entity.selector_ids[0] if entity.selector_ids else None, runtime_resource_id=entity.runtime_resource_id, source=entity.source_layer)
    return deduped


def find_entity(
    entities: list[SemanticEntity],
    *,
    entity_id: str | None = None,
    artifact_id: str | None = None,
    url: str | None = None,
    runtime_resource_id: str | None = None,
    selector: str | None = None,
) -> SemanticEntity | None:
    _debug_v494_semantic_find(
        "START",
        entities=entities,
        requested={
            "entity_id": entity_id,
            "artifact_id": artifact_id,
            "url": url,
            "runtime_resource_id": runtime_resource_id,
            "selector": selector,
        },
    )
    for entity in entities:
        if entity_id and entity.id == entity_id:
            _debug_v494_semantic_find("LOOKUP_ENTITY_ID", entities=entities, requested={"entity_id": entity_id}, matched=entity)
            return entity
    _debug_v494_semantic_find("LOOKUP_ENTITY_ID", entities=entities, requested={"entity_id": entity_id}, failure_reason="requested entity_id missing or no SemanticEntity.id matched")
    for entity in entities:
        if artifact_id and entity.artifact_id == artifact_id:
            _debug_v494_semantic_find("LOOKUP_ARTIFACT_ID", entities=entities, requested={"artifact_id": artifact_id}, matched=entity)
            return entity
    _debug_v494_semantic_find("LOOKUP_ARTIFACT_ID", entities=entities, requested={"artifact_id": artifact_id}, failure_reason="requested artifact_id missing or no SemanticEntity.artifact_id matched")
    for entity in entities:
        candidate_url = entity.canonical_url or entity.url
        if url and candidate_url and candidate_url.rstrip("/") == url.rstrip("/"):
            _debug_v494_semantic_find("LOOKUP_URL", entities=entities, requested={"url": url}, matched=entity)
            return entity
    _debug_v494_semantic_find("LOOKUP_URL", entities=entities, requested={"url": url}, failure_reason="requested url missing or no SemanticEntity canonical/url matched after rstrip('/')")
    for entity in entities:
        if runtime_resource_id and (
            entity.runtime_resource_id == runtime_resource_id
            or entity.browser_bindings.runtime_resource_id == runtime_resource_id
        ):
            _debug_v494_semantic_find("LOOKUP_RUNTIME_RESOURCE_ID", entities=entities, requested={"runtime_resource_id": runtime_resource_id}, matched=entity)
            return entity
    _debug_v494_semantic_find("LOOKUP_RUNTIME_RESOURCE_ID", entities=entities, requested={"runtime_resource_id": runtime_resource_id}, failure_reason="requested runtime_resource_id missing or no SemanticEntity runtime binding matched")
    for entity in entities:
        if selector and (entity.browser_bindings.selector == selector or selector in entity.selector_ids):
            _debug_v494_semantic_find("LOOKUP_SELECTOR", entities=entities, requested={"selector": selector}, matched=entity)
            return entity
    _debug_v494_semantic_find("LOOKUP_SELECTOR", entities=entities, requested={"selector": selector}, failure_reason="requested selector missing or no SemanticEntity selector matched")
    _debug_v494_semantic_find("FINAL_MISS", entities=entities, requested={"entity_id": entity_id, "artifact_id": artifact_id, "url": url, "runtime_resource_id": runtime_resource_id, "selector": selector}, failure_reason="all SemanticEntity lookup strategies missed")
    return None


def _entity_from_element(data: dict[str, Any], source_page: str) -> SemanticEntity | None:
    title = _title(data)
    entity_type = _semantic_type(data)
    url = str(data.get("href") or "") or None
    selector = str(data.get("selector") or "") or None
    selector_id = str(data.get("selector_id") or "") or None
    if not title and not url and not selector and not selector_id:
        return None
    selector_ids = [item for item in (selector_id, selector) if item]
    artifact_id = _artifact_id("page_context", entity_type, url, selector, title)
    return SemanticEntity(
        id=_entity_id(entity_type, title, url, selector),
        semantic_type=entity_type,
        title=title or entity_type,
        url=url,
        confidence=_confidence(data),
        source_page=source_page,
        metadata=_metadata(data),
        browser_bindings=BrowserBinding(selector=selector, selector_id=selector_id, href=url),
        artifact_id=artifact_id,
        canonical_url=url,
        selector_ids=selector_ids,
        source_layer="page_context",
        lifecycle_status="registered",
    )


def _entity_from_block(data: dict[str, Any], source_page: str) -> SemanticEntity | None:
    text = " ".join(str(data.get("text") or "").split())
    href = str(data.get("href") or "") or None
    selector = str(data.get("selector") or "") or None
    if not text and not href and not selector:
        return None
    entity_type = "link" if href else "document"
    title = text[:180] or href or entity_type
    artifact_id = _artifact_id("page_context", entity_type, href, selector, text[:120])
    return SemanticEntity(
        id=_entity_id(entity_type, text[:120], href, selector),
        semantic_type=entity_type,
        title=title,
        url=href,
        confidence=0.78 if href else 0.65,
        source_page=source_page,
        metadata={"text": text[:300]},
        browser_bindings=BrowserBinding(selector=selector, href=href),
        artifact_id=artifact_id,
        canonical_url=href,
        selector_ids=[selector] if selector else [],
        source_layer="page_context",
        lifecycle_status="registered",
    )


def _from_unified_entity(entity: Any) -> SemanticEntity:
    selector = entity.selector_ids[0] if entity.selector_ids else None
    lifecycle = str(entity.state or "REGISTERED").lower()
    allowed = {"discovered", "registered", "grounded", "executing", "executed", "verified", "archived"}
    return SemanticEntity(
        id=entity.entity_id,
        trace_id=entity.trace_id,
        semantic_type=entity.entity_type,
        title=entity.title or entity.entity_type,
        url=entity.canonical_url,
        confidence=entity.confidence,
        source_page=entity.source_page or "",
        metadata=entity.metadata,
        browser_bindings=BrowserBinding(
            selector=selector,
            selector_id=selector,
            href=entity.canonical_url,
            runtime_resource_id=entity.runtime_resource_id,
        ),
        artifact_id=entity.artifact_id,
        canonical_url=entity.canonical_url,
        runtime_resource_id=entity.runtime_resource_id,
        selector_ids=entity.selector_ids,
        source_layer=entity.source_layer,
        lifecycle_status=lifecycle if lifecycle in allowed else "registered",  # type: ignore[arg-type]
    )


def _register_if_scoped(session_id: str | None, entity: SemanticEntity) -> SemanticEntity:
    if not session_id:
        return entity
    unified = register_entity(
        session_id,
        entity_type=entity.semantic_type,
        source_layer=entity.source_layer,
        title=entity.title,
        canonical_url=entity.canonical_url,
        artifact_id=entity.artifact_id,
        selector_ids=entity.selector_ids,
        confidence=entity.confidence,
        source_page=entity.source_page,
        metadata=entity.metadata,
    )
    return _from_unified_entity(unified)


def _semantic_type(data: dict[str, Any]) -> str:
    role = str(data.get("role") or "").lower()
    input_type = str(data.get("input_type") or "").lower()
    tag = str(data.get("type") or data.get("tag") or "").lower()
    text = " ".join(str(data.get(key) or "") for key in ("text", "aria_label", "accessibility_name", "placeholder")).lower()
    if data.get("href") or tag == "a" or role == "link":
        return "link"
    if tag in {"button"} or role == "button":
        return "button"
    if input_type in {"file"}:
        return "file"
    if tag in {"input", "textarea", "select"} or input_type:
        return "form"
    if "table" in role or tag in {"tr", "td", "row"}:
        return "table_row"
    if any(word in text for word in ("message", "email")):
        return "message"
    if "job" in text:
        return "job_posting"
    if any(word in text for word in ("price", "plan", "product")):
        return "product"
    return "document"


def _title(data: dict[str, Any]) -> str:
    for key in ("text", "accessibility_name", "aria_label", "placeholder", "name"):
        value = " ".join(str(data.get(key) or "").split())
        if value:
            return value[:220]
    return ""


def _confidence(data: dict[str, Any]) -> float:
    score = 0.55
    if data.get("selector"):
        score += 0.12
    if data.get("href"):
        score += 0.15
    if _title(data):
        score += 0.12
    if data.get("role") or data.get("accessibility_name"):
        score += 0.06
    return min(score, 0.98)


def _metadata(data: dict[str, Any]) -> dict[str, str]:
    keys = ("role", "input_type", "placeholder", "aria_label", "accessibility_name", "state")
    return {key: str(data.get(key))[:180] for key in keys if data.get(key)}


def _entity_id(entity_type: str, title: Any, url: Any, selector: Any) -> str:
    raw = "|".join([entity_type, str(url or ""), str(selector or ""), str(title or "")])
    return f"ent_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def _artifact_id(source_layer: str, entity_type: str, url: Any, selector: Any, title: Any) -> str:
    raw = "|".join([source_layer, entity_type, str(url or ""), str(selector or ""), str(title or "")])
    return f"{source_layer}:{entity_type}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def _dedupe_entities(entities: list[SemanticEntity]) -> list[SemanticEntity]:
    index_by_key: dict[str, int] = {}
    out: list[SemanticEntity] = []
    for entity in entities:
        key = (entity.canonical_url or entity.url or entity.artifact_id or entity.browser_bindings.selector or entity.title).lower().rstrip("/")
        if key in index_by_key:
            existing = out[index_by_key[key]]
            if existing.source_layer == "page_context" and entity.source_layer != "page_context":
                out[index_by_key[key]] = entity
            continue
        index_by_key[key] = len(out)
        out.append(entity)
    return out


def _debug_v494_semantic_find(
    lookup_type: str,
    *,
    entities: list[SemanticEntity],
    requested: dict[str, Any],
    matched: SemanticEntity | None = None,
    failure_reason: str | None = None,
) -> None:
    try:
        requested_entity_id = requested.get("entity_id")
        requested_artifact_id = requested.get("artifact_id")
        requested_url = requested.get("url")
        requested_selector = requested.get("selector")
        requested_runtime_resource_id = requested.get("runtime_resource_id")
        comparisons = []
        for entity in entities[:120]:
            candidate_url = entity.canonical_url or entity.url
            comparisons.append({
                "entity_id": entity.id,
                "canonical_url": candidate_url,
                "selector_ids": entity.selector_ids[:4],
                "selector": entity.browser_bindings.selector,
                "artifact_id": entity.artifact_id,
                "runtime_resource_id": entity.runtime_resource_id or entity.browser_bindings.runtime_resource_id,
                "entity_id_match": bool(requested_entity_id and entity.id == requested_entity_id),
                "canonical_url_match": bool(requested_url and candidate_url and candidate_url.rstrip("/") == str(requested_url).rstrip("/")),
                "selector_match": bool(requested_selector and (entity.browser_bindings.selector == requested_selector or requested_selector in entity.selector_ids)),
                "artifact_id_match": bool(requested_artifact_id and entity.artifact_id == requested_artifact_id),
                "runtime_resource_id_match": bool(requested_runtime_resource_id and (entity.runtime_resource_id == requested_runtime_resource_id or entity.browser_bindings.runtime_resource_id == requested_runtime_resource_id)),
            })
        print(
            "[V4.9.4 kernel-lookup] SEMANTIC_ENTITY_FIND "
            + json.dumps(
                {
                    "lookup_type": lookup_type,
                    "lookup_input": requested,
                    "lookup_output": "hit" if matched else "miss",
                    "registry_size": len(entities),
                    "matched_entity_id": matched.id if matched else None,
                    "matched_canonical_url": (matched.canonical_url or matched.url) if matched else None,
                    "matched_selector_id": matched.selector_ids[0] if matched and matched.selector_ids else None,
                    "matched_artifact_id": matched.artifact_id if matched else None,
                    "matched_runtime_resource_id": (matched.runtime_resource_id or matched.browser_bindings.runtime_resource_id) if matched else None,
                    "failure_reason": failure_reason,
                    "registry_contents": comparisons,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception as exc:
        print(f"[V4.9.4 kernel-lookup] SEMANTIC_ENTITY_FIND_LOG_FAILED {exc}", flush=True)
