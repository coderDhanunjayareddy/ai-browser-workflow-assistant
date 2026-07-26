from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


EntityState = Literal[
    "DISCOVERED",
    "REGISTERED",
    "GROUNDED",
    "EXECUTING",
    "EXECUTED",
    "VERIFIED",
    "ARCHIVED",
    "INVALID",
]


@dataclass(frozen=True)
class UnifiedEntity:
    trace_id: str
    entity_id: str
    artifact_id: str
    canonical_url: str | None
    runtime_resource_id: str | None
    selector_ids: list[str]
    entity_type: str
    source_layer: str
    title: str
    confidence: float
    state: EntityState
    source_page: str | None
    created_at: int
    updated_at: int
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EntityBindingTraceEvent:
    event: str
    mission_id: str
    registry_name: str
    registry_instance: str
    registry_version: int
    entity_count: int
    thread_id: int
    timestamp: int
    entity_id: str | None = None
    artifact_id: str | None = None
    canonical_url: str | None = None
    runtime_resource_id: str | None = None
    selector_id: str | None = None
    entity_type: str | None = None
    source_layer: str | None = None
    resolved_by: str | None = None
    outcome: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EntityBindingRegistry:
    def __init__(self) -> None:
        self._entities: dict[str, dict[str, UnifiedEntity]] = {}
        self._traces: dict[str, list[EntityBindingTraceEvent]] = {}
        self._version = 0
        self.name = "runtime_state_manager.entity_binding"

    def register(
        self,
        session_id: str,
        *,
        entity_type: str,
        source_layer: str,
        title: str = "",
        canonical_url: str | None = None,
        artifact_id: str | None = None,
        runtime_resource_id: str | None = None,
        selector_ids: list[str] | None = None,
        confidence: float = 0.5,
        source_page: str | None = None,
        metadata: dict[str, Any] | None = None,
        state: EntityState = "REGISTERED",
    ) -> UnifiedEntity:
        now = int(time.time() * 1000)
        normalized_url = _normalize_url(canonical_url)
        selectors = [selector for selector in (selector_ids or []) if selector]
        entity_id = _entity_id(entity_type, normalized_url, artifact_id, selectors, title)
        scoped = self._entities.setdefault(session_id, {})
        previous = scoped.get(entity_id)
        created_at = previous.created_at if previous else now
        merged_metadata = dict(previous.metadata) if previous else {}
        merged_metadata.update({str(k): str(v)[:300] for k, v in dict(metadata or {}).items() if v is not None})
        trace_id = previous.trace_id if previous else str(merged_metadata.get("trace_id") or "")
        if not trace_id:
            from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer

            trace_id = get_entity_pipeline_tracer().trace_id(
                mission_id=session_id,
                entity_id=entity_id,
                artifact_id=artifact_id,
                canonical_url=normalized_url,
                selector_id=selectors[0] if selectors else None,
                source=source_layer,
            )
        merged_metadata["trace_id"] = trace_id
        entity = UnifiedEntity(
            trace_id=trace_id,
            entity_id=entity_id,
            artifact_id=artifact_id or _artifact_id(source_layer, entity_type, normalized_url, selectors, title),
            canonical_url=normalized_url,
            runtime_resource_id=runtime_resource_id or (previous.runtime_resource_id if previous else None),
            selector_ids=sorted(set([*(previous.selector_ids if previous else []), *selectors])),
            entity_type=entity_type,
            source_layer=source_layer,
            title=title[:240] or (previous.title if previous else entity_type),
            confidence=max(confidence, previous.confidence if previous else 0.0),
            state=state,
            source_page=source_page or (previous.source_page if previous else None),
            created_at=created_at,
            updated_at=now,
            metadata=merged_metadata,
        )
        scoped[entity.entity_id] = entity
        self._version += 1
        self._trace(
            "REGISTER_ENTITY",
            session_id,
            entity=entity,
            outcome="success",
            reason=f"{source_layer}:{entity_type}",
        )
        from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer

        get_entity_pipeline_tracer().emit(
            session_id,
            "ENTITY_REGISTRY",
            success=True,
            reason="stored",
            trace_id=entity.trace_id,
            entity_id=entity.entity_id,
            artifact_id=entity.artifact_id,
            canonical_url=entity.canonical_url,
            selector_id=entity.selector_ids[0] if entity.selector_ids else None,
            runtime_resource_id=entity.runtime_resource_id,
            source=entity.source_layer,
        )
        return entity

    def list(self, session_id: str) -> list[UnifiedEntity]:
        entities = list(self._entities.get(session_id, {}).values())
        self._trace("REGISTRY_INSTANCE", session_id, outcome="snapshot", reason=f"entity_count={len(entities)}")
        from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer

        get_entity_pipeline_tracer().emit(
            session_id,
            "ENTITY_REGISTRY",
            success=True,
            reason="snapshot",
            count=len(entities),
        )
        return entities

    def resolve(
        self,
        session_id: str,
        *,
        entity_id: str | None = None,
        artifact_id: str | None = None,
        canonical_url: str | None = None,
        runtime_resource_id: str | None = None,
        selector_id: str | None = None,
    ) -> UnifiedEntity | None:
        entities = list(self._entities.get(session_id, {}).values())
        self._trace("REGISTRY_INSTANCE", session_id, outcome="lookup_start", reason=f"entity_count={len(entities)}")
        normalized_url = _normalize_url(canonical_url)
        for entity in entities:
            if entity_id and entity.entity_id == entity_id:
                self._trace_lookup(session_id, "LOOKUP_ENTITY_ID", "HIT", entity=entity, entity_id=entity_id, resolved_by="entity_id")
                return entity
        self._trace_lookup(session_id, "LOOKUP_ENTITY_ID", "MISS", entity_id=entity_id)
        for entity in entities:
            if artifact_id and entity.artifact_id == artifact_id:
                self._trace_lookup(session_id, "LOOKUP_ARTIFACT_ID", "HIT", entity=entity, artifact_id=artifact_id, resolved_by="artifact_id")
                return entity
        self._trace_lookup(session_id, "LOOKUP_ARTIFACT_ID", "MISS", artifact_id=artifact_id)
        for entity in entities:
            if normalized_url and entity.canonical_url == normalized_url:
                self._trace_lookup(session_id, "LOOKUP_CANONICAL_URL", "HIT", entity=entity, canonical_url=normalized_url, resolved_by="canonical_url")
                return entity
        self._trace_lookup(session_id, "LOOKUP_CANONICAL_URL", "MISS", canonical_url=normalized_url)
        for entity in entities:
            if runtime_resource_id and entity.runtime_resource_id == runtime_resource_id:
                self._trace_lookup(session_id, "LOOKUP_RUNTIME_RESOURCE_ID", "HIT", entity=entity, runtime_resource_id=runtime_resource_id, resolved_by="runtime_resource_id")
                return entity
        self._trace_lookup(session_id, "LOOKUP_RUNTIME_RESOURCE_ID", "MISS", runtime_resource_id=runtime_resource_id)
        for entity in entities:
            if selector_id and selector_id in entity.selector_ids:
                self._trace_lookup(session_id, "LOOKUP_SELECTOR_ID", "HIT", entity=entity, selector_id=selector_id, resolved_by="selector_id")
                return entity
        self._trace_lookup(session_id, "LOOKUP_SELECTOR_ID", "MISS", selector_id=selector_id)
        return None

    def bind_runtime_resource(
        self,
        session_id: str,
        *,
        entity_id: str,
        runtime_resource_id: str,
        state: EntityState = "EXECUTED",
    ) -> UnifiedEntity | None:
        entity = self.resolve(session_id, entity_id=entity_id)
        if entity is None:
            self._trace("RUNTIME_BINDING", session_id, entity_id=entity_id, runtime_resource_id=runtime_resource_id, outcome="failure", reason="entity_missing")
            return None
        bound = self.register(
            session_id,
            entity_type=entity.entity_type,
            source_layer=entity.source_layer,
            title=entity.title,
            canonical_url=entity.canonical_url,
            artifact_id=entity.artifact_id,
            runtime_resource_id=runtime_resource_id,
            selector_ids=entity.selector_ids,
            confidence=entity.confidence,
            source_page=entity.source_page,
            metadata=entity.metadata,
            state=state,
        )
        self._trace("RUNTIME_BINDING", session_id, entity=bound, runtime_resource_id=runtime_resource_id, outcome="success")
        from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer

        get_entity_pipeline_tracer().emit(
            session_id,
            "RUNTIME",
            success=True,
            reason="bound",
            trace_id=bound.trace_id,
            entity_id=bound.entity_id,
            artifact_id=bound.artifact_id,
            canonical_url=bound.canonical_url,
            runtime_resource_id=runtime_resource_id,
            source=bound.source_layer,
        )
        return bound

    def invalidate_runtime_resource(self, session_id: str, runtime_resource_id: str) -> int:
        count = 0
        for entity in self.list(session_id):
            if entity.runtime_resource_id == runtime_resource_id:
                self.register(
                    session_id,
                    entity_type=entity.entity_type,
                    source_layer=entity.source_layer,
                    title=entity.title,
                    canonical_url=entity.canonical_url,
                    artifact_id=entity.artifact_id,
                    runtime_resource_id=runtime_resource_id,
                    selector_ids=entity.selector_ids,
                    confidence=entity.confidence,
                    source_page=entity.source_page,
                    metadata=entity.metadata,
                    state="ARCHIVED",
                )
                count += 1
        return count

    def trace(self, session_id: str, *, limit: int = 80) -> list[EntityBindingTraceEvent]:
        return self._traces.get(session_id, [])[-limit:]

    def registry_identity(self, session_id: str) -> dict[str, Any]:
        return {
            "registry_name": self.name,
            "registry_instance": hex(id(self)),
            "registry_version": self._version,
            "mission_id": session_id,
            "entity_count": len(self._entities.get(session_id, {})),
            "thread_id": threading.get_ident(),
        }

    def _trace(
        self,
        event: str,
        session_id: str,
        *,
        entity: UnifiedEntity | None = None,
        entity_id: str | None = None,
        artifact_id: str | None = None,
        canonical_url: str | None = None,
        runtime_resource_id: str | None = None,
        selector_id: str | None = None,
        entity_type: str | None = None,
        source_layer: str | None = None,
        resolved_by: str | None = None,
        outcome: str | None = None,
        reason: str | None = None,
    ) -> None:
        trace = EntityBindingTraceEvent(
            event=event,
            mission_id=session_id,
            registry_name=self.name,
            registry_instance=hex(id(self)),
            registry_version=self._version,
            entity_count=len(self._entities.get(session_id, {})),
            thread_id=threading.get_ident(),
            timestamp=int(time.time() * 1000),
            entity_id=entity.entity_id if entity else entity_id,
            artifact_id=entity.artifact_id if entity else artifact_id,
            canonical_url=entity.canonical_url if entity else canonical_url,
            runtime_resource_id=entity.runtime_resource_id if entity else runtime_resource_id,
            selector_id=(entity.selector_ids[0] if entity and entity.selector_ids else selector_id),
            entity_type=entity.entity_type if entity else entity_type,
            source_layer=entity.source_layer if entity else source_layer,
            resolved_by=resolved_by,
            outcome=outcome,
            reason=reason,
        )
        self._traces.setdefault(session_id, []).append(trace)
        self._traces[session_id] = self._traces[session_id][-300:]
        logger.info("V4.9.2 entity trace: %s", trace.to_dict())

    def _trace_lookup(
        self,
        session_id: str,
        event: str,
        outcome: str,
        *,
        entity: UnifiedEntity | None = None,
        entity_id: str | None = None,
        artifact_id: str | None = None,
        canonical_url: str | None = None,
        runtime_resource_id: str | None = None,
        selector_id: str | None = None,
        resolved_by: str | None = None,
    ) -> None:
        self._trace(
            event,
            session_id,
            entity=entity,
            entity_id=entity_id,
            artifact_id=artifact_id,
            canonical_url=canonical_url,
            runtime_resource_id=runtime_resource_id,
            selector_id=selector_id,
            resolved_by=resolved_by,
            outcome=outcome,
        )


def register_browser_intelligence_artifact(session_id: str, artifact: Any) -> list[UnifiedEntity]:
    page_model = getattr(artifact, "page_model", None)
    if page_model is None:
        return []
    source_page = str(getattr(page_model, "url", "") or "")
    from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer

    tracer = get_entity_pipeline_tracer()
    discovered_count = len(list(getattr(page_model, "search_results", []) or [])[:40]) + len([
        element
        for element in list(getattr(page_model, "elements", []) or [])[:120]
        if str(getattr(element, "href", "") or "") or str(getattr(element, "selector", "") or "") or str(getattr(element, "selector_id", "") or "")
    ])
    tracer.emit(session_id, "DOM_SCAN", success=True, reason="entity found", count=discovered_count, source="browser_intelligence")
    registered: list[UnifiedEntity] = []
    for result in list(getattr(page_model, "search_results", []) or [])[:40]:
        registered.append(
            _registry.register(
                session_id,
                entity_type="search_result",
                source_layer="browser_intelligence",
                title=str(getattr(result, "title", "") or ""),
                canonical_url=str(getattr(result, "url", "") or "") or None,
                artifact_id=f"bi:search_result:{_hash(source_page)}:{getattr(result, 'rank', 0)}",
                selector_ids=[str(getattr(result, "selector_id", "") or ""), str(getattr(result, "open_selector", "") or "")],
                confidence=0.92,
                source_page=source_page,
                metadata={
                    "rank": getattr(result, "rank", ""),
                    "displayed_url": getattr(result, "displayed_url", ""),
                    "description": getattr(result, "description", ""),
                },
            )
        )
    for element in list(getattr(page_model, "elements", []) or [])[:120]:
        href = str(getattr(element, "href", "") or "") or None
        selector = str(getattr(element, "selector", "") or "") or None
        selector_id = str(getattr(element, "selector_id", "") or "") or None
        if not href and not selector and not selector_id:
            continue
        registered.append(
            _registry.register(
                session_id,
                entity_type=str(getattr(element, "kind", "") or "element"),
                source_layer="browser_intelligence",
                title=str(getattr(element, "label", "") or ""),
                canonical_url=href,
                artifact_id=f"bi:element:{getattr(element, 'element_id', '') or _hash(str(selector or href))}",
                selector_ids=[item for item in (selector_id, selector) if item],
                confidence=float(getattr(element, "confidence", 0.5) or 0.5),
                source_page=source_page,
                metadata={"role": getattr(element, "role", "") or ""},
            )
        )
    tracer.verify_count(
        session_id,
        stage="ENTITY_REGISTRY",
        reason="BrowserIntelligence -> EntityRegistry registered_count == discovered_count",
        expected=discovered_count,
        actual=len(registered),
    )
    return registered


def register_entity(session_id: str, **kwargs: Any) -> UnifiedEntity:
    return _registry.register(session_id, **kwargs)


def resolve_entity(session_id: str, **kwargs: Any) -> UnifiedEntity | None:
    return _registry.resolve(session_id, **kwargs)


def list_entities(session_id: str) -> list[UnifiedEntity]:
    return _registry.list(session_id)


def entity_binding_trace(session_id: str, *, limit: int = 80) -> list[dict[str, Any]]:
    return [event.to_dict() for event in _registry.trace(session_id, limit=limit)]


def registry_identity(session_id: str) -> dict[str, Any]:
    return _registry.registry_identity(session_id)


def bind_runtime_resource(session_id: str, **kwargs: Any) -> UnifiedEntity | None:
    return _registry.bind_runtime_resource(session_id, **kwargs)


def invalidate_runtime_resource(session_id: str, runtime_resource_id: str) -> int:
    return _registry.invalidate_runtime_resource(session_id, runtime_resource_id)


def binding_telemetry(session_id: str) -> dict[str, Any]:
    entities = list_entities(session_id)
    traces = entity_binding_trace(session_id, limit=120)
    hits = [trace for trace in traces if str(trace.get("event", "")).startswith("LOOKUP_") and trace.get("outcome") == "HIT"]
    misses = [trace for trace in traces if str(trace.get("event", "")).startswith("LOOKUP_") and trace.get("outcome") == "MISS"]
    bound = [entity for entity in entities if entity.runtime_resource_id]
    stale = [entity for entity in entities if entity.state in {"ARCHIVED", "INVALID"}]
    return {
        "entity_registered": len(entities),
        "entity_resolved": len(hits),
        "entity_binding_latency": 0,
        "registry_lookup_latency": 0,
        "binding_failures": len([trace for trace in traces if trace.get("event") == "RUNTIME_BINDING" and trace.get("outcome") == "failure"]),
        "runtime_sync_failures": 0,
        "stale_entity_count": len(stale),
        "identity_resolution_success_rate": round(len(hits) / max(1, len(hits) + len(misses)), 3),
        "cross_layer_sync_latency": 0,
        "runtime_bound_entity_count": len(bound),
        "registry_instance": registry_identity(session_id),
    }


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}{query}"


def _entity_id(entity_type: str, canonical_url: str | None, artifact_id: str | None, selector_ids: list[str], title: str) -> str:
    stable = canonical_url or artifact_id or "|".join(selector_ids) or title
    return "ent_" + _hash(f"{entity_type}|{stable}")


def _artifact_id(source_layer: str, entity_type: str, canonical_url: str | None, selector_ids: list[str], title: str) -> str:
    stable = canonical_url or "|".join(selector_ids) or title
    return f"{source_layer}:{entity_type}:{_hash(stable)}"


def _hash(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]


_registry = EntityBindingRegistry()
