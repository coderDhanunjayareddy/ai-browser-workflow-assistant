from __future__ import annotations

import hashlib
import logging
import inspect
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

from app.feature_flags import is_active, is_shadow_or_active
from app.schemas.response import AnalyzeResponse, ReplanOutcome

logger = logging.getLogger(__name__)


PipelineStage = Literal[
    "DOM_SCAN",
    "ENTITY_EXTRACTION",
    "ENTITY_REGISTRY",
    "PLANNER_CONTEXT",
    "PROMPT_BUILDER",
    "PLANNER_RESPONSE",
    "SEMANTIC_KERNEL",
    "GROUNDING",
    "RUNTIME",
    "BROWSER_CONTROL",
]


@dataclass(frozen=True)
class EntityPipelineEvent:
    timestamp: int
    mission_id: str
    stage: str
    success: bool
    reason: str
    trace_id: str | None = None
    entity_id: str | None = None
    artifact_id: str | None = None
    canonical_url: str | None = None
    title: str | None = None
    selector_id: str | None = None
    runtime_resource_id: str | None = None
    source: str | None = None
    count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EntityPipelineFailure:
    stage: str
    reason: str
    created_at: int = 0
    origin_file: str | None = None
    origin_function: str | None = None
    expected: int | None = None
    actual: int | None = None
    trace_id: str | None = None
    entity_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EntityPipelineTracer:
    def __init__(self) -> None:
        self._events: dict[str, list[EntityPipelineEvent]] = {}
        self._failures: dict[str, list[EntityPipelineFailure]] = {}
        self._lock = threading.Lock()

    def trace_id(
        self,
        *,
        mission_id: str,
        entity_id: str | None,
        artifact_id: str | None,
        canonical_url: str | None,
        selector_id: str | None,
        source: str | None,
    ) -> str:
        stable = "|".join(
            str(part or "")
            for part in (mission_id, entity_id, artifact_id, canonical_url, selector_id, source)
        )
        return f"trace_{hashlib.sha1(stable.encode('utf-8')).hexdigest()[:16]}_{uuid.uuid4().hex[:8]}"

    def emit(
        self,
        mission_id: str,
        stage: PipelineStage | str,
        *,
        success: bool,
        reason: str,
        trace_id: str | None = None,
        entity_id: str | None = None,
        artifact_id: str | None = None,
        canonical_url: str | None = None,
        title: str | None = None,
        selector_id: str | None = None,
        runtime_resource_id: str | None = None,
        source: str | None = None,
        count: int | None = None,
    ) -> None:
        if not is_shadow_or_active("V493_ENTITY_PIPELINE_TRACE"):
            return
        event = EntityPipelineEvent(
            timestamp=int(time.time() * 1000),
            mission_id=mission_id,
            stage=str(stage),
            success=success,
            reason=reason,
            trace_id=trace_id,
            entity_id=entity_id,
            artifact_id=artifact_id,
            canonical_url=canonical_url,
            title=title,
            selector_id=selector_id,
            runtime_resource_id=runtime_resource_id,
            source=source,
            count=count,
        )
        with self._lock:
            self._events.setdefault(mission_id, []).append(event)
            self._events[mission_id] = self._events[mission_id][-1200:]
        logger.info("V4.9.3 entity pipeline trace: %s", event.to_dict())

    def verify_count(
        self,
        mission_id: str,
        *,
        stage: str,
        reason: str,
        expected: int,
        actual: int,
        comparator: Literal["eq", "gte"] = "eq",
    ) -> EntityPipelineFailure | None:
        if not is_shadow_or_active("V493_ENTITY_PIPELINE_TRACE"):
            return None
        ok = actual == expected if comparator == "eq" else actual >= expected
        self.emit(mission_id, stage, success=ok, reason=reason, count=actual)
        if ok:
            return None
        failure = EntityPipelineFailure(stage=stage, reason=reason, expected=expected, actual=actual)
        self._record_failure(mission_id, failure)
        return failure

    def verify_exists(
        self,
        mission_id: str,
        *,
        stage: str,
        reason: str,
        exists: bool,
        trace_id: str | None = None,
        entity_id: str | None = None,
    ) -> EntityPipelineFailure | None:
        if not is_shadow_or_active("V493_ENTITY_PIPELINE_TRACE"):
            return None
        self.emit(mission_id, stage, success=exists, reason=reason, trace_id=trace_id, entity_id=entity_id)
        if exists:
            return None
        failure = EntityPipelineFailure(stage=stage, reason=reason, trace_id=trace_id, entity_id=entity_id)
        self._record_failure(mission_id, failure)
        return failure

    def events(self, mission_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return [event.to_dict() for event in self._events.get(mission_id, [])[-limit:]]

    def failures(self, mission_id: str) -> list[EntityPipelineFailure]:
        with self._lock:
            return list(self._failures.get(mission_id, []))

    def telemetry(self, mission_id: str) -> dict[str, Any]:
        events = self.events(mission_id, limit=1200)
        failures = self.failures(mission_id)
        return {
            "browser_intelligence_entities": _last_count(events, "BROWSER_INTELLIGENCE"),
            "semantic_element_count": _last_count(events, "SEMANTIC_EXTRACTION"),
            "entities_discovered": _last_count(events, "DOM_SCAN"),
            "entities_registered": _last_count(events, "ENTITY_REGISTRY"),
            "entities_sent_to_planner": _last_count(events, "PLANNER_CONTEXT"),
            "prompt_entity_count": _last_count(events, "PROMPT_BUILDER"),
            "planner_response_entity_reference_valid": _latest_success(events, "PLANNER_RESPONSE"),
            "entities_received_by_kernel": _last_count(events, "SEMANTIC_KERNEL"),
            "entities_grounded": _success_count(events, "GROUNDING"),
            "entities_bound": _success_count(events, "RUNTIME"),
            "entities_executed": _success_count(events, "BROWSER_CONTROL"),
            "contract_failures": len(failures),
            "pipeline_stage_failure": failures[-1].stage if failures else None,
        }

    def timeline(self, mission_id: str) -> list[dict[str, Any]]:
        events = self.events(mission_id, limit=1200)
        timeline: list[dict[str, Any]] = []
        for stage in ("DOM_SCAN", "ENTITY_REGISTRY", "PLANNER_CONTEXT", "SEMANTIC_KERNEL", "GROUNDING", "RUNTIME", "BROWSER_CONTROL"):
            stage_events = [event for event in events if event.get("stage") == stage]
            if not stage_events:
                continue
            latest = stage_events[-1]
            count = latest.get("count")
            if count is None:
                count = sum(1 for event in stage_events if event.get("success"))
            timeline.append({"stage": stage, "count": count, "success": latest.get("success"), "reason": latest.get("reason")})
        failures = self.failures(mission_id)
        if failures:
            timeline.append({"stage": "FAIL", "count": 1, "success": False, "reason": failures[-1].reason})
        return timeline

    def replay(self, mission_id: str) -> dict[str, Any]:
        events = self.events(mission_id, limit=1200)
        return {
            "discovered_entities": _entities_for(events, "DOM_SCAN"),
            "registered_entities": _entities_for(events, "ENTITY_REGISTRY"),
            "planner_entities": _entities_for(events, "PLANNER_CONTEXT"),
            "kernel_entities": _entities_for(events, "SEMANTIC_KERNEL"),
            "grounded_entities": _entities_for(events, "GROUNDING"),
            "runtime_bindings": _entities_for(events, "RUNTIME"),
            "browser_executions": _entities_for(events, "BROWSER_CONTROL"),
            "timeline": self.timeline(mission_id),
            "failures": [failure.to_dict() for failure in self.failures(mission_id)],
        }

    def active_failure_response(self, result: AnalyzeResponse, mission_id: str) -> AnalyzeResponse | None:
        if not (
            is_active("V493_ENTITY_PIPELINE_TRACE")
            or is_active("V451_BROWSER_INTELLIGENCE_PLANNER_CONTEXT")
        ):
            return None
        failures = self.failures(mission_id)
        if not failures:
            return None
        failure = failures[-1]
        return AnalyzeResponse(
            session_id=result.session_id,
            analysis=f"{result.analysis}\n\nENTITY_PIPELINE_FAILURE\nstage: {failure.stage}\nreason: {failure.reason}",
            outcome_kind="replan",
            clarification_question=None,
            report=None,
            replan=ReplanOutcome(reason=f"ENTITY_PIPELINE_FAILURE stage={failure.stage} reason={failure.reason}"),
            suggested_actions=[],
        )

    def _record_failure(self, mission_id: str, failure: EntityPipelineFailure) -> None:
        origin = _failure_origin()
        stamped = EntityPipelineFailure(
            stage=failure.stage,
            reason=failure.reason,
            created_at=failure.created_at or int(time.time() * 1000),
            origin_file=failure.origin_file or origin.get("file"),
            origin_function=failure.origin_function or origin.get("function"),
            expected=failure.expected,
            actual=failure.actual,
            trace_id=failure.trace_id,
            entity_id=failure.entity_id,
        )
        with self._lock:
            self._failures.setdefault(mission_id, []).append(stamped)
            self._failures[mission_id] = self._failures[mission_id][-80:]


def _last_count(events: list[dict[str, Any]], stage: str) -> int:
    for event in reversed(events):
        if event.get("stage") == stage and event.get("count") is not None:
            return int(event.get("count") or 0)
    return sum(1 for event in events if event.get("stage") == stage and event.get("success"))


def _success_count(events: list[dict[str, Any]], stage: str) -> int:
    return sum(1 for event in events if event.get("stage") == stage and event.get("success") and event.get("trace_id"))


def _latest_success(events: list[dict[str, Any]], stage: str) -> bool | None:
    for event in reversed(events):
        if event.get("stage") == stage:
            return bool(event.get("success"))
    return None


def _failure_origin() -> dict[str, str | None]:
    for frame in inspect.stack()[2:10]:
        filename = frame.filename.replace("\\", "/")
        if not filename.endswith("entity_pipeline_trace.py"):
            return {"file": frame.filename, "function": frame.function}
    return {"file": None, "function": None}


def _entities_for(events: list[dict[str, Any]], stage: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        if event.get("stage") != stage or not event.get("trace_id"):
            continue
        key = str(event.get("trace_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "trace_id": event.get("trace_id"),
            "entity_id": event.get("entity_id"),
            "artifact_id": event.get("artifact_id"),
            "canonical_url": event.get("canonical_url"),
            "title": event.get("title"),
            "selector_id": event.get("selector_id"),
            "runtime_resource_id": event.get("runtime_resource_id"),
            "source": event.get("source"),
            "success": event.get("success"),
            "reason": event.get("reason"),
        })
    return out


_tracer = EntityPipelineTracer()


def get_entity_pipeline_tracer() -> EntityPipelineTracer:
    return _tracer


def entity_pipeline_telemetry(mission_id: str) -> dict[str, Any]:
    return _tracer.telemetry(mission_id)


def entity_pipeline_replay(mission_id: str) -> dict[str, Any]:
    return _tracer.replay(mission_id)


def browser_intelligence_entity_summary(mission_id: str, artifact: Any) -> list[dict[str, Any]]:
    page_model = getattr(artifact, "page_model", None)
    if page_model is None:
        return []
    from app.runtime_state_manager.entity_binding import resolve_entity

    summaries: list[dict[str, Any]] = []
    for result in list(getattr(page_model, "search_results", []) or []):
        unified = resolve_entity(mission_id, canonical_url=str(getattr(result, "url", "") or ""))
        summaries.append(_entity_summary(
            trace_id=getattr(unified, "trace_id", None),
            entity_id=getattr(unified, "entity_id", None),
            artifact_id=getattr(unified, "artifact_id", None),
            canonical_url=getattr(unified, "canonical_url", None) or str(getattr(result, "url", "") or ""),
            title=str(getattr(result, "title", "") or ""),
            confidence=0.92,
            source_adapter=str(getattr(page_model, "adapter", "") or ""),
            source="browser_intelligence.search_results",
        ))
    seen = {item["canonical_url"] or item["entity_id"] or item["title"] for item in summaries}
    for element in list(getattr(page_model, "elements", []) or []):
        href = str(getattr(element, "href", "") or "")
        selector_id = str(getattr(element, "selector_id", "") or "")
        unified = resolve_entity(mission_id, canonical_url=href or None, selector_id=selector_id or None)
        key = getattr(unified, "canonical_url", None) or href or getattr(unified, "entity_id", None) or str(getattr(element, "label", "") or "")
        if key in seen:
            continue
        seen.add(key)
        summaries.append(_entity_summary(
            trace_id=getattr(unified, "trace_id", None),
            entity_id=getattr(unified, "entity_id", None),
            artifact_id=getattr(unified, "artifact_id", None),
            canonical_url=getattr(unified, "canonical_url", None) or href or None,
            title=str(getattr(element, "label", "") or ""),
            confidence=float(getattr(element, "confidence", 0.5) or 0.5),
            source_adapter=str(getattr(page_model, "adapter", "") or ""),
            source=f"browser_intelligence.{getattr(element, 'kind', 'element')}",
        ))
    return [item for item in summaries if item.get("entity_id") or item.get("canonical_url") or item.get("title")]


def record_browser_intelligence_output(mission_id: str, artifact: Any) -> list[dict[str, Any]]:
    if not is_shadow_or_active("V451_BROWSER_INTELLIGENCE_PLANNER_CONTEXT"):
        return []
    page_model = getattr(artifact, "page_model", None)
    summaries = browser_intelligence_entity_summary(mission_id, artifact)
    semantic_elements = list(getattr(page_model, "elements", []) or []) if page_model else []
    content_kinds = {"card", "table", "list", "search_result", "text"}
    has_content_entities = any(str(getattr(element, "kind", "") or "") in content_kinds for element in semantic_elements)
    _tracer.emit(
        mission_id,
        "SEMANTIC_EXTRACTION",
        success=has_content_entities,
        reason="semantic elements discovered" if has_content_entities else "No semantic content extracted.",
        count=len(semantic_elements),
        source=str(getattr(page_model, "adapter", "") or "") if page_model else None,
    )
    _tracer.emit(
        mission_id,
        "BROWSER_INTELLIGENCE",
        success=True,
        reason="semantic output recorded",
        count=len(summaries),
        source=str(getattr(page_model, "adapter", "") or "") if page_model else None,
    )
    for entity in summaries:
        _tracer.emit(
            mission_id,
            "BROWSER_INTELLIGENCE",
            success=True,
            reason="entity discovered",
            trace_id=entity.get("trace_id"),
            entity_id=entity.get("entity_id"),
            artifact_id=entity.get("artifact_id"),
            canonical_url=entity.get("canonical_url"),
            title=entity.get("title"),
            source=entity.get("source_adapter"),
        )
    if semantic_elements and not has_content_entities:
        _tracer.verify_exists(
            mission_id,
            stage="SemanticExtraction",
            reason="No semantic content extracted.",
            exists=False,
        )
    return summaries


def record_planner_context_entities(mission_id: str, compressed_context: dict[str, Any], *, browser_entity_count: int | None = None) -> list[dict[str, Any]]:
    if not is_shadow_or_active("V451_BROWSER_INTELLIGENCE_PLANNER_CONTEXT"):
        return []
    entities = planner_context_entities(compressed_context)
    _tracer.emit(mission_id, "PLANNER_CONTEXT", success=True, reason="browser intelligence entities injected", count=len(entities))
    for entity in entities:
        _tracer.emit(
            mission_id,
            "PLANNER_CONTEXT",
            success=True,
            reason="included",
            trace_id=entity.get("trace_id"),
            entity_id=entity.get("entity_id"),
            artifact_id=entity.get("artifact_id"),
            canonical_url=entity.get("canonical_url"),
            title=entity.get("title"),
            source=entity.get("source_adapter"),
        )
    if browser_entity_count is not None:
        _tracer.verify_count(
            mission_id,
            stage="PlannerContext",
            reason="Entity omitted during prompt construction.",
            expected=browser_entity_count,
            actual=len(entities),
        )
    return entities


def record_prompt_entities(mission_id: str, compressed_context: dict[str, Any]) -> list[dict[str, Any]]:
    if not is_shadow_or_active("V451_BROWSER_INTELLIGENCE_PLANNER_CONTEXT"):
        return []
    entities = planner_context_entities(compressed_context)
    _tracer.emit(mission_id, "PROMPT_BUILDER", success=True, reason="semantic entities injected", count=len(entities))
    for entity in entities:
        _tracer.emit(
            mission_id,
            "PROMPT_BUILDER",
            success=True,
            reason="injected",
            trace_id=entity.get("trace_id"),
            entity_id=entity.get("entity_id"),
            artifact_id=entity.get("artifact_id"),
            canonical_url=entity.get("canonical_url"),
            title=entity.get("title"),
            source=entity.get("source_adapter"),
        )
    return entities


def verify_planner_response_entities(mission_id: str, result: AnalyzeResponse, compressed_context: dict[str, Any] | None) -> None:
    if not compressed_context or not is_shadow_or_active("V451_BROWSER_INTELLIGENCE_PLANNER_CONTEXT"):
        return
    if not result.suggested_actions:
        return
    action = result.suggested_actions[0]
    value = str(action.value or "")
    if not value.startswith(("http://", "https://")):
        return
    entities = planner_context_entities(compressed_context)
    allowed_urls = {str(entity.get("canonical_url") or "").rstrip("/") for entity in entities if entity.get("canonical_url")}
    ok = value.rstrip("/") in allowed_urls
    _tracer.emit(mission_id, "PLANNER_RESPONSE", success=ok, reason="planner response references observed entity" if ok else "planner response URL was not in prompt entities", canonical_url=value)
    if not ok:
        _tracer.verify_exists(
            mission_id,
            stage="PlannerResponse",
            reason="Planner response referenced an entity that was not injected into the prompt.",
            exists=False,
        )


def planner_context_entities(compressed_context: dict[str, Any]) -> list[dict[str, Any]]:
    browser_intelligence = compressed_context.get("browser_intelligence") if isinstance(compressed_context, dict) else None
    if not isinstance(browser_intelligence, dict):
        return []
    raw = browser_intelligence.get("semantic_entities") or []
    return [item for item in raw if isinstance(item, dict)]


def _entity_summary(
    *,
    trace_id: str | None,
    entity_id: str | None,
    artifact_id: str | None,
    canonical_url: str | None,
    title: str,
    confidence: float,
    source_adapter: str,
    source: str,
) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "entity_id": entity_id,
        "artifact_id": artifact_id,
        "canonical_url": canonical_url,
        "title": title[:180],
        "confidence": confidence,
        "source_adapter": source_adapter,
        "source": source,
    }
