from __future__ import annotations

import json

from app.feature_flags import is_shadow_or_active
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.semantic_page.builder import SemanticPageGraphBuilder
from app.semantic_page.cache import SemanticGraphCache
from app.semantic_page.graph import SemanticPageGraph


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
            InteractiveElement(
                type="button",
                text="Download",
                selector="#download",
                visible=True,
            ),
        ],
        selected_text="",
        visible_text="Search Results Lightpanda browser automation repository Playwright browser automation docs",
    )


def test_semantic_graph_generation_is_deterministic_byte_for_byte():
    builder = SemanticPageGraphBuilder()

    first = builder.build(sample_page()).to_stable_json()
    second = builder.build(sample_page()).to_stable_json()

    assert first == second


def test_semantic_graph_snapshot_shape():
    graph = SemanticPageGraphBuilder().build(sample_page())

    assert graph.schema_version == "semantic_page_graph.v1"
    assert graph.builder_version == "v1"
    assert graph.page_type == "search_results"
    assert [node.node_type for node in graph.nodes] == [
        "page",
        "section",
        "result_set",
        "result_item",
        "result_item",
        "control",
        "field",
        "download",
    ]
    assert [target.semantic_role for target in graph.targets] == [
        "navigate_link",
        "search_field",
        "download_file",
    ]
    assert graph.metadata["source"] == "dom_a11y"
    assert graph.metadata["build_ms"] == 0


def test_semantic_graph_serialization_round_trips_stably():
    graph = SemanticPageGraphBuilder().build(sample_page())
    serialized = graph.to_stable_json()
    loaded = SemanticPageGraph.model_validate(json.loads(serialized))

    assert loaded.to_stable_json() == serialized
    assert loaded.graph_id == graph.graph_id


def test_semantic_graph_cache_is_versioned_bounded_and_reports_hits():
    cache = SemanticGraphCache(max_entries=1, ttl_seconds=60)

    first = cache.get_or_build(sample_page())
    second = cache.get_or_build(sample_page())
    other_page = sample_page()
    other_page.url = "https://example.test/other"
    third = cache.get_or_build(other_page)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert third.cache_hit is False
    assert cache.size() == 1
    assert cache.cache_key(sample_page()).startswith("semantic_page_graph.v1:v1:")


def test_semantic_graph_feature_flag_default_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_semantic_graph", "shadow")
    assert is_shadow_or_active("V3_SEMANTIC_GRAPH") is True

    monkeypatch.setattr(settings, "v3_semantic_graph", "off")
    assert is_shadow_or_active("V3_SEMANTIC_GRAPH") is False


def test_semantic_graph_generation_meets_budget_for_typical_observation():
    result = SemanticGraphCache(max_entries=4).get_or_build(sample_page())

    assert result.build_ms < 80
    assert len(result.graph.nodes) <= 8
    assert len(result.graph.targets) == 3
