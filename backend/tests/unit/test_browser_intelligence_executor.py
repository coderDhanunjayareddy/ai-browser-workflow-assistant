from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective
from app.intent_providers.browser_intelligence_executor import execute


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
