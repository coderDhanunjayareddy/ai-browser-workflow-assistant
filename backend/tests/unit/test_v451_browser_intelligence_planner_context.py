from __future__ import annotations

import pytest

from app.browser_intelligence import build_browser_intelligence, format_browser_intelligence_for_planner
from app.core.config import settings
from app.runtime_state_manager.entity_binding import list_entities
from app.runtime_state_manager.entity_pipeline_trace import (
    entity_pipeline_replay,
    entity_pipeline_telemetry,
    planner_context_entities,
    record_planner_context_entities,
    record_prompt_entities,
    verify_planner_response_entities,
)
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.semantic_execution_kernel.engine import SemanticExecutionKernel


def _page(kind: str) -> PageContext:
    fixtures = {
        "search": {
            "url": "https://www.bing.com/search?q=firecrawl",
            "title": "firecrawl - Search",
            "elements": [
                InteractiveElement(type="a", selector="#r1", text="Firecrawl", href="https://firecrawl.dev", visible=True),
                InteractiveElement(type="a", selector="#r2", text="Firecrawl GitHub", href="https://github.com/mendableai/firecrawl", visible=True),
            ],
            "blocks": [
                ContentBlock(selector="#card-r1", href="https://firecrawl.dev", text="Firecrawl Turn websites into LLM-ready data."),
                ContentBlock(selector="#card-r2", href="https://github.com/mendableai/firecrawl", text="GitHub mendableai/firecrawl open source web crawler."),
            ],
        },
        "jobs": {
            "url": "https://jobs.example.test/search",
            "title": "Jobs",
            "elements": [],
            "blocks": [
                ContentBlock(selector="[data-job='1']", href="https://jobs.example.test/1", text="Senior Backend Engineer Remote Apply now"),
                ContentBlock(selector="[data-job='2']", href="https://jobs.example.test/2", text="Data Platform Engineer Salary remote listing"),
            ],
        },
        "docs": {
            "url": "https://docs.example.test",
            "title": "Documentation",
            "elements": [],
            "blocks": [
                ContentBlock(selector="#quickstart", href="https://docs.example.test/quickstart", text="Quickstart Install the SDK and create your first API request."),
                ContentBlock(selector="#api-reference", href="https://docs.example.test/api", text="API Reference Authentication endpoints and request examples."),
            ],
        },
        "directory": {
            "url": "https://directory.example.test/tools",
            "title": "Tool Directory",
            "elements": [],
            "blocks": [
                ContentBlock(selector=".tool:nth-child(1)", href="https://directory.example.test/tools/alpha", text="Alpha Analytics dashboard connector"),
                ContentBlock(selector=".tool:nth-child(2)", href="https://directory.example.test/tools/beta", text="Beta Reports SaaS dashboard"),
            ],
        },
        "pricing": {
            "url": "https://saas.example.test/pricing",
            "title": "Pricing",
            "elements": [],
            "blocks": [
                ContentBlock(selector="#pro-plan", href="https://saas.example.test/pricing/pro", text="Pro plan $29 per month includes reports"),
                ContentBlock(selector="#enterprise-plan", href="https://saas.example.test/pricing/enterprise", text="Enterprise custom price SSO support"),
            ],
        },
    }
    fixture = fixtures[kind]
    return PageContext(
        url=fixture["url"],
        title=fixture["title"],
        metadata={},
        interactive_elements=fixture["elements"],
        content_blocks=fixture["blocks"],
        headings=[fixture["title"]],
        selected_text="",
        visible_text="\n".join(block.text for block in fixture["blocks"]),
        images=[],
    )


@pytest.mark.parametrize("kind", ["search", "jobs", "docs", "directory", "pricing"])
def test_browser_intelligence_entities_reach_planner_context_and_prompt(monkeypatch, kind):
    monkeypatch.setattr(settings, "v451_browser_intelligence_planner_context", "shadow")
    session_id = f"v451-{kind}"
    artifact = build_browser_intelligence(_page(kind), scope_id=session_id)
    planner_context = {"browser_intelligence": format_browser_intelligence_for_planner(artifact, scope_id=session_id)}

    injected = record_planner_context_entities(
        session_id,
        planner_context,
        browser_entity_count=len(planner_context["browser_intelligence"]["semantic_entities"]),
    )
    prompted = record_prompt_entities(session_id, planner_context)

    assert len(planner_context["browser_intelligence"]["semantic_entities"]) >= 2
    assert len(injected) == len(prompted)
    assert {entity["entity_id"] for entity in injected} == {entity["entity_id"] for entity in prompted}
    assert list_entities(session_id)
    assert entity_pipeline_telemetry(session_id)["entities_sent_to_planner"] >= 2
    assert entity_pipeline_telemetry(session_id)["prompt_entity_count"] == len(prompted)


def test_planner_response_references_valid_prompt_entity_and_kernel_resolves(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    monkeypatch.setattr(settings, "v451_browser_intelligence_planner_context", "shadow")
    session_id = "v451-valid-response"
    page = _page("directory")
    artifact = build_browser_intelligence(page, scope_id=session_id)
    planner_context = {"browser_intelligence": format_browser_intelligence_for_planner(artifact, scope_id=session_id)}
    observed = planner_context_entities(planner_context)
    target = observed[0]["canonical_url"]
    response = AnalyzeResponse(
        session_id=session_id,
        analysis="Open the observed directory entity.",
        outcome_kind="act",
        suggested_actions=[
            SuggestedAction(
                action_id="open-observed",
                action_type="open_new_tab",  # type: ignore[arg-type]
                target_selector="",
                value=target,
                description="Open observed entity",
                reasoning="The URL is present in Browser Intelligence semantic entities.",
                confidence=0.9,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )

    verify_planner_response_entities(session_id, response, planner_context)
    result = SemanticExecutionKernel().postprocess_response(
        result=response,
        session_id=session_id,
        task="Open the first directory entity.",
        page_context=page,
        prior_steps=[],
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].value == target


def test_semantic_extraction_failure_when_only_controls(monkeypatch):
    monkeypatch.setattr(settings, "v451_browser_intelligence_planner_context", "shadow")
    session_id = "v451-controls-only"
    page = PageContext(
        url="https://app.example.test",
        title="Header",
        metadata={},
        interactive_elements=[
            InteractiveElement(type="button", selector="#logo", text="Logo", visible=True),
            InteractiveElement(type="input", selector="#search", text="", placeholder="Search", visible=True),
        ],
        content_blocks=[],
        headings=["Header"],
        selected_text="",
        visible_text="Logo Search",
        images=[],
    )

    build_browser_intelligence(page, scope_id=session_id)
    replay = entity_pipeline_replay(session_id)

    assert any(
        failure["stage"] == "SemanticExtraction" and "No semantic content extracted" in failure["reason"]
        for failure in replay["failures"]
    )
