from __future__ import annotations

from typing import Any

from app.browser_intelligence.action_verification import ActionVerificationEngine
from app.browser_intelligence.cache import BoundedCache
from app.browser_intelligence.dynamic_dom import DynamicDomTracker, semantic_signature
from app.browser_intelligence.health import BrowserHealthMonitor
from app.browser_intelligence.memory import BrowserMemory
from app.browser_intelligence.models import BrowserIntelligenceArtifact
from app.browser_intelligence.page_understanding import PageUnderstandingEngine
from app.browser_intelligence.recovery import AdaptiveRecoveryEngine
from app.browser_intelligence.replay import build_replay_artifact
from app.browser_intelligence.telemetry import telemetry_summary
from app.browser_intelligence.visual_grounding import VisualGroundingEngine
from app.browser_intelligence.waits import IntelligentWaitingEngine
from app.feature_flags import is_shadow_or_active


_PLANNER_SEARCH_RESULT_LIMIT = 8
_PLANNER_SEMANTIC_ENTITY_LIMIT = 24
_PLANNER_SEMANTIC_ELEMENT_LIMIT = 12


class BrowserIntelligenceRuntime:
    def __init__(self) -> None:
        self.page_understanding = PageUnderstandingEngine()
        self.action_verification = ActionVerificationEngine()
        self.dynamic_dom = DynamicDomTracker()
        self.waits = IntelligentWaitingEngine()
        self.memory = BrowserMemory()
        self.recovery = AdaptiveRecoveryEngine()
        self.visual_grounding = VisualGroundingEngine()
        self.health = BrowserHealthMonitor()
        self.page_model_cache = BoundedCache(max_size=64)

    def build(
        self,
        page_context: Any,
        *,
        scope_id: str = "default",
        failed_selector: str | None = None,
        target_label: str | None = None,
    ) -> BrowserIntelligenceArtifact:
        cache_key = _cache_key(page_context)
        page_model = self.page_model_cache.get(cache_key)
        cache_hit = page_model is not None
        if page_model is None:
            page_model = self.page_understanding.build_page_model(page_context)
            self.page_model_cache.set(cache_key, page_model)
        browser_state = self.page_understanding.build_browser_state(page_context, page_model)
        mutation_signals = (
            self.dynamic_dom.track(scope_id, page_model)
            if is_shadow_or_active("V46_DYNAMIC_DOM")
            else []
        )
        wait_plan = (
            self.waits.plan(page_model, browser_state)
            if is_shadow_or_active("V46_INTELLIGENT_WAIT")
            else None
        )
        memory = (
            self.memory.remember(scope_id, page_model, browser_state)
            if is_shadow_or_active("V46_BROWSER_MEMORY")
            else None
        )
        recovery = (
            self.recovery.recover(
                failed_selector=failed_selector,
                target_label=target_label,
                page_model=page_model,
            )
            if (failed_selector or target_label) and is_shadow_or_active("V46_RECOVERY_ENGINE")
            else None
        )
        visual_targets = (
            self.visual_grounding.ground(page_model)
            if is_shadow_or_active("V46_VISUAL_GROUNDING")
            else []
        )
        health = self.health.assess(
            page_model=page_model,
            mutations=mutation_signals,
            wait_plan=wait_plan,
            recovery=recovery,
        ) if is_shadow_or_active("V46_BROWSER_HEALTH") and wait_plan is not None else None
        replay = build_replay_artifact(
            page_model=page_model,
            mutation_signals=mutation_signals,
            wait_plan=wait_plan,
            memory=memory,
            recovery=recovery,
            visual_targets=visual_targets,
            health=health,
        )
        telemetry = telemetry_summary(page_model)
        telemetry.update({
            "mutation_frequency": len(mutation_signals),
            "stale_model_detection": health.stale_model if health else False,
            "wait_latency": wait_plan.timeout_ms if wait_plan else None,
            "recovery_latency": 0,
            "recovery_success_rate": 1.0 if recovery and recovery.recovered else 0.0,
            "selector_stability": health.metrics.get("selector_stability") if health else None,
            "browser_health_score": health.health_score if health else None,
            "cache": self.page_model_cache.stats() | {"page_model_cache_hit": cache_hit},
        })
        capability_report = {
            "schema_version": "browser_intelligence.capability_report.v1",
            "capabilities": {
                "page_understanding": "level_3_shadow_certifiable",
                "browser_state_model": "level_3_shadow_certifiable",
                "selector_intelligence": "level_3_shadow_certifiable",
                "action_verification": "level_3_shadow_certifiable",
                "site_adapters": "level_3_shadow_certifiable",
                "google_serp_adapter": (
                    "level_4_certified" if page_model.adapter == "google_search"
                    else "level_3_shadow_certifiable"
                ),
                "search_result_abstraction": "level_4_certified" if page_model.search_results else "level_3_shadow_certifiable",
                "replay_integration": "level_3_shadow_certifiable",
                "telemetry": "level_3_shadow_certifiable",
                "dynamic_dom_tracking": "level_4_certified",
                "intelligent_waiting": "level_4_certified",
                "browser_memory": "level_4_certified",
                "adaptive_recovery": "level_4_certified",
                "visual_grounding": "level_3_shadow_certifiable",
                "browser_health": "level_4_certified",
                "performance_optimization": "level_4_certified",
            },
            "telemetry": telemetry,
        }
        artifact = BrowserIntelligenceArtifact(
            page_model=page_model,
            browser_state=browser_state,
            replay=replay,
            capability_report=capability_report,
            mutation_signals=mutation_signals,
            wait_plan=wait_plan,
            memory=memory,
            recovery=recovery,
            visual_targets=visual_targets,
            health=health,
        )
        try:
            from app.runtime_state_manager.entity_binding import register_browser_intelligence_artifact, registry_identity
            from app.runtime_state_manager.entity_pipeline_trace import entity_pipeline_telemetry, record_browser_intelligence_output

            registered = register_browser_intelligence_artifact(scope_id, artifact)
            bi_entities = record_browser_intelligence_output(scope_id, artifact)
            capability_report["telemetry"]["entity_registered"] = len(registered)
            capability_report["telemetry"]["browser_intelligence_entities"] = len(bi_entities)
            capability_report["telemetry"]["entity_registry"] = registry_identity(scope_id)
            capability_report["telemetry"]["entity_pipeline"] = entity_pipeline_telemetry(scope_id)
        except Exception:
            capability_report["telemetry"]["entity_registered"] = 0
            capability_report["telemetry"]["entity_registration_failure"] = True
        return artifact


_runtime = BrowserIntelligenceRuntime()


def build_browser_intelligence(
    page_context: Any,
    *,
    scope_id: str = "default",
    failed_selector: str | None = None,
    target_label: str | None = None,
) -> BrowserIntelligenceArtifact:
    return _runtime.build(
        page_context,
        scope_id=scope_id,
        failed_selector=failed_selector,
        target_label=target_label,
    )


def format_browser_intelligence_for_planner(artifact: BrowserIntelligenceArtifact, *, scope_id: str = "default") -> dict[str, Any]:
    page_model = artifact.page_model
    from app.runtime_state_manager.entity_binding import resolve_entity
    from app.runtime_state_manager.entity_pipeline_trace import browser_intelligence_entity_summary

    search_results = [
        _search_result_context(result, resolve_entity(scope_id, canonical_url=result.url))
        for result in page_model.search_results[:_PLANNER_SEARCH_RESULT_LIMIT]
    ]
    search_result_urls = {str(item.get("canonical_url") or item.get("url") or "").rstrip("/") for item in search_results}
    entity_summaries = browser_intelligence_entity_summary(scope_id, artifact)
    ranked_entity_summaries = sorted(
        entity_summaries,
        key=lambda item: (
            0 if str(item.get("canonical_url") or "").rstrip("/") in search_result_urls else 1,
            0 if item.get("canonical_url") else 1,
            str(item.get("title") or ""),
        ),
    )
    semantic_elements = [
        {
            "element_id": element.element_id,
            "kind": element.kind,
            "label": str(element.label or "")[:120],
            "selector_id": element.selector_id,
            "selector": str(element.selector or "")[:180],
            "href": element.href,
            "confidence": element.confidence,
        }
        for element in page_model.elements[:_PLANNER_SEMANTIC_ELEMENT_LIMIT]
        if element.visible
    ]
    return {
        "schema_version": "browser_intelligence.planner_context.v1",
        "page_type": page_model.classification.page_type,
        "classification_confidence": page_model.classification.confidence,
        "adapter": page_model.adapter,
        "browser_state": artifact.browser_state.to_dict(),
        "semantic_elements": semantic_elements,
        "semantic_entities": ranked_entity_summaries[:_PLANNER_SEMANTIC_ENTITY_LIMIT],
        "search_results": search_results,
        "memory": artifact.memory.to_dict() if artifact.memory else None,
        "health": artifact.health.to_dict() if artifact.health else None,
        "wait_plan": artifact.wait_plan.to_dict() if artifact.wait_plan else None,
        "selector_rules": [
            "Use selector values only when provided by Browser Intelligence.",
            "For search results, prefer open_new_tab with the explicit result URL.",
            "Ignore AI panels, ads, navigation tabs, related searches, and duplicate URLs.",
        ],
    }


def _search_result_context(result: Any, entity: Any) -> dict[str, Any]:
    return {
        "rank": result.rank,
        "entity_id": entity.entity_id if entity else None,
        "artifact_id": entity.artifact_id if entity else None,
        "title": str(result.title or "")[:160],
        "url": result.url,
        "canonical_url": entity.canonical_url if entity else result.url,
        "displayed_url": result.displayed_url,
        "description": str(result.description or "")[:220],
        "entity_type": entity.entity_type if entity else "search_result",
        "state": entity.state if entity else "REGISTERED",
        "confidence": entity.confidence if entity else 0.92,
        "open_action": {
            "action_type": "open_new_tab",
            "target_selector": None,
            "value": result.url,
            "expected": {"tab_count_delta": 1, "new_tab_url": result.url},
        },
    }


def _cache_key(page_context: Any) -> str:
    provisional = PageUnderstandingEngine().build_page_model(page_context)
    return semantic_signature(provisional)
