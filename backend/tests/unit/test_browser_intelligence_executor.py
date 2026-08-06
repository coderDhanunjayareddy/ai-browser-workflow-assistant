from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective
from app.intent_providers.browser_intelligence_executor import execute
from app.runtime_state_manager.entity_binding import list_entities


def _directive() -> IntentDispatchDirective:
    return IntentDispatchDirective(
        mission_id="serp-test",
        intent="collect_search_results",
        owner="browser_intelligence",
        capability="serp_collection",
        dispatch_target="browser_intelligence",
        reason="Collect observed SERP results.",
    )


def test_collects_serp_results_from_serialized_page_context_content_blocks():
    context = ExecutionContext(
        mission_id="serp-test",
        task="Search browser automation tools",
        page_context={
            "content_blocks": [
                {
                    "href": "https://www.firecrawl.dev/blog/best-browser-agents",
                    "text": "11 Best AI Browser Agents in 2026",
                    "selector": "a[href='https://www.firecrawl.dev/blog/best-browser-agents']",
                },
                {
                    "href": "https://www.browserstack.com/guide/best-browser-automation-tool",
                    "text": "Top 12 Browser Automation Tools in 2026",
                    "selector": "a[href='https://www.browserstack.com/guide/best-browser-automation-tool']",
                },
            ]
        },
    )

    result = execute(context, _directive())

    results = result.evidence[0].payload["search_results"]
    assert result.status == "succeeded"
    assert result.evidence[0].payload["search_result_count"] == 2
    assert results[0]["title"] == "11 Best AI Browser Agents in 2026"
    assert results[0]["url"] == "https://www.firecrawl.dev/blog/best-browser-agents"
    assert context.metadata["browser_intelligence"]["search_results"] == results


def test_collects_serp_results_from_serialized_semantic_page_model():
    context = ExecutionContext(
        mission_id="serp-test",
        task="Search browser automation tools",
        browser_intelligence={
            "page_model": {
                "search_results": [
                    {
                        "rank": 1,
                        "title": "Best Browser Automation Tools",
                        "description": "A comparison of browser automation tools.",
                        "url": "https://example.com/tools",
                        "displayed_url": "example.com/tools",
                    }
                ]
            }
        },
    )

    result = execute(context, _directive())

    results = result.evidence[0].payload["search_results"]
    assert result.evidence[0].payload["search_result_count"] == 1
    assert results[0]["snippet"] == "A comparison of browser automation tools."
    assert results[0]["url"] == "https://example.com/tools"
    assert results[0]["normalized_url"] == "https://example.com/tools"
    assert results[0]["source_domain"] == "example.com"
    assert results[0]["source_type"] == "unknown"
    assert results[0]["is_ad"] is False
    assert results[0]["relevance_score"] == 0.5


def test_collects_serp_results_dedupes_same_url_fragments():
    context = ExecutionContext(
        mission_id="serp-test",
        task="Search browser automation tools",
        browser_intelligence={
            "page_model": {
                "search_results": [
                    {"rank": 1, "title": "AI Browsers", "url": "https://example.com/ai-browsers"},
                    {"rank": 2, "title": "AI Browsers Overview", "url": "https://example.com/ai-browsers#overview"},
                    {"rank": 3, "title": "Automation Tools", "url": "https://example.com/tools"},
                ]
            }
        },
    )

    result = execute(context, _directive())

    results = result.evidence[0].payload["search_results"]
    assert [item["url"] for item in results] == [
        "https://example.com/ai-browsers",
        "https://example.com/tools",
    ]
    assert [item["rank"] for item in results] == [1, 2]
    assert [item["normalized_url"] for item in results] == [
        "https://example.com/ai-browsers",
        "https://example.com/tools",
    ]


def test_collects_serp_results_preserves_semantic_source_fields():
    context = ExecutionContext(
        mission_id="serp-test",
        task="Search browser automation tools",
        browser_intelligence={
            "page_model": {
                "search_results": [
                    {
                        "rank": 1,
                        "title": "AI Browser Agents",
                        "url": "https://example.com/agents",
                        "normalized_url": "https://example.com/agents/",
                        "source_domain": "example.com",
                        "source_type": "organic",
                        "is_ad": False,
                        "relevance_score": 0.8,
                    }
                ]
            }
        },
    )

    result = execute(context, _directive())

    item = result.evidence[0].payload["search_results"][0]
    assert item["source_type"] == "organic"
    assert item["source_domain"] == "example.com"
    assert item["normalized_url"] == "https://example.com/agents"
    assert item["relevance_score"] == 0.8


def test_collect_search_results_registers_ranked_entities_for_open_phase():
    context = ExecutionContext(
        mission_id="serp-entity-registration",
        task="Open Google Search and search for: `best AI browser automation tools 2026`. Open the top 5 relevant results.",
        page_context={"url": "https://www.google.com/search?q=best+AI+browser+automation+tools+2026"},
        browser_intelligence={
            "page_model": {
                "search_results": [
                    {"rank": 1, "title": "Tool A", "url": "https://tool-a.example/pricing", "relevance_score": 0.91},
                    {"rank": 2, "title": "Tool B", "url": "https://tool-b.example/docs", "relevance_score": 0.84},
                ]
            }
        },
    )

    result = execute(context, _directive())

    payload = result.evidence[0].payload
    entities = [entity for entity in list_entities("serp-entity-registration") if entity.entity_type == "search_result"]
    assert payload["registered_entity_count"] == 2
    assert payload["source_collection_policy"]["requested_source_count"] == 5
    assert payload["source_collection_policy"]["available_source_count"] == 2
    assert [entity.canonical_url for entity in entities] == [
        "https://tool-a.example/pricing",
        "https://tool-b.example/docs",
    ]
    assert entities[0].metadata["rank"] == "1"


def test_collect_search_results_filters_ads_and_unwraps_google_redirects():
    context = ExecutionContext(
        mission_id="serp-filtering",
        task="Search and summarize browser automation sources.",
        browser_intelligence={
            "page_model": {
                "search_results": [
                    {"rank": 1, "title": "Ad", "url": "https://ad.example/", "is_ad": True},
                    {"rank": 2, "title": "Google Search", "url": "https://www.google.com/search?q=other"},
                    {"rank": 3, "title": "External", "url": "https://www.google.com/url?q=https%3A%2F%2Fexternal.example%2Fguide&sa=U"},
                ]
            }
        },
    )

    result = execute(context, _directive())

    results = result.evidence[0].payload["search_results"]
    assert len(results) == 1
    assert results[0]["url"] == "https://www.google.com/url?q=https%3A%2F%2Fexternal.example%2Fguide&sa=U"
    assert results[0]["normalized_url"] == "https://external.example/guide"
    assert results[0]["source_domain"] == "external.example"
