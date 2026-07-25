from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse


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


class EntityBindingRegistry:
    def __init__(self) -> None:
        self._entities: dict[str, dict[str, UnifiedEntity]] = {}

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
        entity = UnifiedEntity(
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
        return entity

    def list(self, session_id: str) -> list[UnifiedEntity]:
        return list(self._entities.get(session_id, {}).values())

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
        entities = self.list(session_id)
        normalized_url = _normalize_url(canonical_url)
        for entity in entities:
            if entity_id and entity.entity_id == entity_id:
                return entity
        for entity in entities:
            if artifact_id and entity.artifact_id == artifact_id:
                return entity
        for entity in entities:
            if normalized_url and entity.canonical_url == normalized_url:
                return entity
        for entity in entities:
            if runtime_resource_id and entity.runtime_resource_id == runtime_resource_id:
                return entity
        for entity in entities:
            if selector_id and selector_id in entity.selector_ids:
                return entity
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
            return None
        return self.register(
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


def register_browser_intelligence_artifact(session_id: str, artifact: Any) -> list[UnifiedEntity]:
    page_model = getattr(artifact, "page_model", None)
    if page_model is None:
        return []
    source_page = str(getattr(page_model, "url", "") or "")
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
    return registered


def register_entity(session_id: str, **kwargs: Any) -> UnifiedEntity:
    return _registry.register(session_id, **kwargs)


def resolve_entity(session_id: str, **kwargs: Any) -> UnifiedEntity | None:
    return _registry.resolve(session_id, **kwargs)


def list_entities(session_id: str) -> list[UnifiedEntity]:
    return _registry.list(session_id)


def bind_runtime_resource(session_id: str, **kwargs: Any) -> UnifiedEntity | None:
    return _registry.bind_runtime_resource(session_id, **kwargs)


def invalidate_runtime_resource(session_id: str, runtime_resource_id: str) -> int:
    return _registry.invalidate_runtime_resource(session_id, runtime_resource_id)


def binding_telemetry(session_id: str) -> dict[str, Any]:
    entities = list_entities(session_id)
    bound = [entity for entity in entities if entity.runtime_resource_id]
    stale = [entity for entity in entities if entity.state in {"ARCHIVED", "INVALID"}]
    return {
        "entity_registered": len(entities),
        "entity_resolved": 0,
        "entity_binding_latency": 0,
        "registry_lookup_latency": 0,
        "binding_failures": 0,
        "runtime_sync_failures": 0,
        "stale_entity_count": len(stale),
        "identity_resolution_success_rate": 1.0 if entities else 0.0,
        "cross_layer_sync_latency": 0,
        "runtime_bound_entity_count": len(bound),
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
