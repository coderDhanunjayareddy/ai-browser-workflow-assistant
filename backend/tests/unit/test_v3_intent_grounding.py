from __future__ import annotations

from app.context_packet.builder import ContextPacketBuilder
from app.feature_flags import is_shadow_or_active
from app.grounding import GroundingCache, GroundingResolver
from app.grounding.telemetry import record_grounding_metrics
from app.observability.metrics import default_metric_sink
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.schemas.response import SuggestedAction
from app.semantic_page.builder import SemanticPageGraphBuilder
from app.semantic_page.graph import SemanticPageGraph, SemanticTarget


def sample_page() -> PageContext:
    return PageContext(
        url="https://example.test/search?q=browser",
        title="Search Results",
        metadata={"lang": "en"},
        headings=["Results"],
        content_blocks=[
            ContentBlock(selector="#r1", text="Lightpanda browser automation repository"),
            ContentBlock(selector="#r2", text="Playwright browser automation docs"),
        ],
        interactive_elements=[
            InteractiveElement(
                type="a",
                text="lightpanda-io/browser",
                selector='a[href="/lightpanda-io/browser"]',
                visible=True,
                role="link",
                accessibility_name="lightpanda-io/browser repository",
            ),
            InteractiveElement(
                type="input",
                text="",
                selector="#search",
                visible=True,
                input_type="search",
                placeholder="Search",
                role="searchbox",
            ),
        ],
        selected_text="",
        visible_text="Search Results Lightpanda browser automation repository Playwright browser automation docs",
    )


def click_repository_action(selector: str = 'a[href="/lightpanda-io/browser"]') -> SuggestedAction:
    return SuggestedAction(
        action_id="act-1",
        action_type="click",
        target_selector=selector,
        value=None,
        description="Open repository page",
        reasoning="Open the browser automation repository result",
        confidence=0.8,
        safety_level="safe",
    )


def test_grounding_resolves_semantic_target_from_graph():
    graph = SemanticPageGraphBuilder().build(sample_page())

    result = GroundingResolver().resolve(
        run_id="run-1",
        action=click_repository_action(),
        graph=graph,
    )

    assert result.schema_version == "grounding_result.v1"
    assert result.status == "resolved"
    assert result.semantic_target_id == "target.navigate_link.1"
    assert result.selected_selector == 'a[href="/lightpanda-io/browser"]'
    assert result.confidence >= 0.55
    assert result.replay_metadata["graph_id"] == graph.graph_id


def test_grounding_decision_is_deterministic_for_identical_inputs():
    graph = SemanticPageGraphBuilder().build(sample_page())
    resolver = GroundingResolver()

    first = resolver.resolve(run_id="run-1", action=click_repository_action(), graph=graph)
    second = resolver.resolve(run_id="run-1", action=click_repository_action(), graph=graph)

    assert first.status == second.status
    assert first.semantic_target_id == second.semantic_target_id
    assert first.selected_selector == second.selected_selector
    assert first.confidence == second.confidence
    assert [candidate.model_dump() for candidate in first.candidates] == [
        candidate.model_dump() for candidate in second.candidates
    ]


def test_grounding_detects_ambiguous_targets():
    graph = SemanticPageGraph(
        graph_id="graph.ambiguous",
        observation_id="obs.ambiguous",
        url="https://example.test",
        title="Settings",
        page_type="page",
        targets=[
            SemanticTarget(
                target_id="target.activate_control.1",
                target_type="button",
                semantic_role="activate_control",
                label="Settings",
                locator_candidates=["#settings-a"],
                confidence=0.9,
            ),
            SemanticTarget(
                target_id="target.activate_control.2",
                target_type="button",
                semantic_role="activate_control",
                label="Settings",
                locator_candidates=["#settings-b"],
                confidence=0.9,
            ),
        ],
    )
    action = SuggestedAction(
        action_id="act-ambiguous",
        action_type="click",
        target_selector="",
        description="Open Settings",
        reasoning="Click the Settings control",
        confidence=0.7,
        safety_level="safe",
    )

    result = GroundingResolver().resolve(run_id="run-1", action=action, graph=graph)

    assert result.status == "ambiguous"
    assert result.ambiguity_reason == "multiple_semantic_targets_with_similar_confidence"
    assert len(result.candidates) == 2


def test_grounding_uses_legacy_selector_fallback_when_semantic_target_missing():
    graph = SemanticPageGraphBuilder().build(sample_page())
    action = SuggestedAction(
        action_id="act-fallback",
        action_type="click",
        target_selector="#legacy-only",
        value=None,
        description="Open billing portal",
        reasoning="Click billing portal control",
        confidence=0.7,
        safety_level="safe",
    )

    result = GroundingResolver().resolve(
        run_id="run-1",
        action=action,
        graph=graph,
    )

    assert result.status == "fallback"
    assert result.fallback_used is True
    assert result.selected_selector == "#legacy-only"
    assert result.fallback_reason == "semantic_target_not_resolved_using_legacy_selector"


def test_grounding_cache_is_versioned_bounded_and_reports_hits():
    graph = SemanticPageGraphBuilder().build(sample_page())
    cache = GroundingCache(max_entries=1, ttl_seconds=60)
    resolver = GroundingResolver()
    action = click_repository_action()

    first = cache.get_or_resolve(
        run_id="run-1",
        action=action,
        graph=graph,
        resolver=resolver,
    )
    second = cache.get_or_resolve(
        run_id="run-1",
        action=action,
        graph=graph,
        resolver=resolver,
    )

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.result.cache_hit is True
    assert cache.size() == 1
    assert cache.cache_key(action=action, graph=graph).startswith("grounding_result.v1:")


def test_grounding_replay_metadata_includes_packet_and_graph_versions():
    page = sample_page()
    graph = SemanticPageGraphBuilder().build(page)
    packet, _build_ms = ContextPacketBuilder().build(
        run_id="run-1",
        task="Open repository",
        page_context=page,
        semantic_graph=graph,
        prior_steps=[],
        supplemental_context="",
        verified_facts={},
        compressed_context={"active_goal": "Open repository"},
    )

    result = GroundingResolver().resolve(
        run_id="run-1",
        action=click_repository_action(),
        graph=graph,
        packet=packet,
    )

    assert result.replay_metadata["semantic_graph_version"] == "semantic_page_graph.v1"
    assert result.replay_metadata["planner_packet_version"] == "planner_packet.v1"
    assert result.replay_metadata["candidate_count"] >= 1


def test_intent_grounding_feature_flag_default_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_intent_grounding", "shadow")
    assert is_shadow_or_active("V3_INTENT_GROUNDING") is True

    monkeypatch.setattr(settings, "v3_intent_grounding", "off")
    assert is_shadow_or_active("V3_INTENT_GROUNDING") is False


def test_grounding_resolution_meets_budget_for_typical_observation():
    graph = SemanticPageGraphBuilder().build(sample_page())

    result = GroundingCache(max_entries=4).get_or_resolve(
        run_id="run-1",
        action=click_repository_action(),
        graph=graph,
        resolver=GroundingResolver(),
    )

    assert result.resolve_ms < 30
    assert result.result.status == "resolved"


def test_grounding_telemetry_records_resolution_metrics():
    graph = SemanticPageGraphBuilder().build(sample_page())
    cache_result = GroundingCache(max_entries=4).get_or_resolve(
        run_id="run-telemetry",
        action=click_repository_action(),
        graph=graph,
        resolver=GroundingResolver(),
    )

    before = len(default_metric_sink.snapshot())
    record_grounding_metrics(
        "run-telemetry",
        cache_result,
        hit_ratio=0.0,
        cache_size=1,
    )
    recorded = default_metric_sink.snapshot()[before:]

    assert {point.name for point in recorded} >= {
        "v3.grounding.latency_ms",
        "v3.grounding.confidence",
        "v3.grounding.cache_hit_ratio",
        "v3.grounding.resolved",
    }
