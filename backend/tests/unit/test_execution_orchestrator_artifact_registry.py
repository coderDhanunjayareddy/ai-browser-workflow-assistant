from __future__ import annotations

from app.execution_orchestrator.artifact_registry import build_artifacts
from app.schemas.request import PageContext, PriorStep


def _page() -> PageContext:
    return PageContext(
        url="https://www.google.com/search?q=ai+tools",
        title="Google Search",
        metadata={},
        interactive_elements=[],
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="",
        images=[],
    )


def test_opened_pages_prefer_structured_browser_evidence_url() -> None:
    artifacts = build_artifacts(
        _page(),
        [
            PriorStep(
                action_type="open_new_tab",
                description="Open ranked result",
                target_selector="",
                value="result:1",
                execution_result="Opened new tab: https://tool.example/pricing",
                page_url="https://www.google.com/search?q=ai+tools",
                page_title="Google Search",
                browser_evidence={
                    "opened_tab_id": 123,
                    "tab_switch_verified": True,
                    "page_url": "https://tool.example/pricing",
                    "page_title": "Tool Pricing",
                },
            )
        ],
    )

    assert artifacts.opened_pages == ["https://tool.example/pricing"]
    assert "https://tool.example/pricing" in artifacts.visited_urls
