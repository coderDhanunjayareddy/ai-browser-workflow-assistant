from __future__ import annotations

from app.browser_intelligence import (
    build_browser_intelligence,
    format_browser_intelligence_for_planner,
)
from app.browser_intelligence.action_verification import ActionVerificationEngine
from app.browser_intelligence.adapters import GoogleSearchAdapter
from app.browser_intelligence.page_understanding import PageUnderstandingEngine
from app.browser_intelligence.selector_engine import SelectorIntelligenceEngine
from app.capability_platform.browser_registry import get_browser_capability
from app.feature_flags import get_flag_state, v4_flag_snapshot
from app.schemas.request import ContentBlock, InteractiveElement, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.services.ai_service import _postprocess_planner_response


def _google_serp_context() -> PageContext:
    return PageContext(
        url="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
        title="best AI browser automation tools 2026 - Google Search",
        metadata={},
        interactive_elements=[
            InteractiveElement(
                type="a",
                text="AI Overview",
                selector='a[href="/search?sca_esv=ai_mode"]',
                visible=True,
                href="https://www.google.com/search?sca_esv=ai_mode",
            ),
            InteractiveElement(
                type="a",
                text="Sponsored result",
                selector='a[href="https://ads.google.com/example"]',
                visible=True,
                href="https://ads.google.com/example",
            ),
            InteractiveElement(
                type="a",
                text="Browser Use",
                selector='a[href="https://browser-use.com/"]',
                visible=True,
                href="https://browser-use.com/",
            ),
            InteractiveElement(
                type="a",
                text="Playwright",
                selector='a[href="https://playwright.dev/"]',
                visible=True,
                href="https://playwright.dev/",
            ),
            InteractiveElement(
                type="a",
                text="Browser Use duplicate",
                selector='a[href="https://browser-use.com/"]',
                visible=True,
                href="https://browser-use.com/",
            ),
        ],
        content_blocks=[
            ContentBlock(
                selector='div[role="heading"]:nth-of-type(1)',
                text="AI Overview Search with AI Mode People also ask",
            ),
            ContentBlock(
                selector='a[href="https://browser-use.com/"]',
                text="Browser Use Browser automation for AI agents. Pricing Free and paid plans.",
                href="https://browser-use.com/",
            ),
            ContentBlock(
                selector='a[href="https://playwright.dev/"]',
                text="Playwright Fast and reliable end-to-end testing for modern web apps.",
                href="https://playwright.dev/",
            ),
        ],
        headings=["Search results"],
        selected_text="",
        visible_text="AI Overview People also ask Browser Use Playwright",
        images=[],
    )


def _google_serp_context_with_five_results() -> PageContext:
    elements = [
        InteractiveElement(
            type="a",
            text=f"Tool {index}",
            selector=f'a[href="https://tool{index}.example/"]',
            visible=True,
            href=f"https://tool{index}.example/",
        )
        for index in range(1, 6)
    ]
    return PageContext(
        url="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
        title="best AI browser automation tools 2026 - Google Search",
        metadata={},
        interactive_elements=elements,
        content_blocks=[
            ContentBlock(
                selector=element.selector,
                text=f"{element.text} Browser automation platform.",
                href=element.href,
            )
            for element in elements
        ],
        headings=["Search results"],
        selected_text="",
        visible_text=" ".join(element.text for element in elements),
        images=[],
    )


def test_v45_flags_default_to_shadow():
    flags = v4_flag_snapshot()
    assert flags["V45_BROWSER_INTELLIGENCE"] == "shadow"
    assert flags["V45_SERP_ADAPTER"] == "shadow"
    assert get_flag_state("V45_PAGE_MODEL").value == "shadow"


def test_v45_capability_registry_has_browser_intelligence_records():
    serp = get_browser_capability("browser_intelligence.search.google_serp")
    selectors = get_browser_capability("browser_intelligence.selectors")
    assert serp is not None
    assert serp.feature_flag == "V45_SERP_ADAPTER"
    assert serp.maturity_level == 4
    assert "v45.google_serp.ai_overview_exclusion" in serp.benchmarks
    assert selectors is not None
    assert selectors.feature_flag == "V45_SELECTOR_ENGINE"


def test_google_serp_adapter_extracts_external_organic_results_only():
    adapter = GoogleSearchAdapter()
    context = _google_serp_context()
    results = adapter.getOrganicResults(context)
    assert [result.title for result in results] == ["Browser Use", "Playwright"]
    assert [result.rank for result in results] == [1, 2]
    assert all("google.com" not in result.displayed_url for result in results)
    assert len({result.url for result in results}) == len(results)


def test_google_open_result_returns_open_new_tab_expectation():
    opened = GoogleSearchAdapter().openResult(_google_serp_context(), 2)
    assert opened["ok"] is True
    assert opened["action_type"] == "open_new_tab"
    assert opened["value"] == "https://playwright.dev/"
    assert opened["expected"]["tab_count_delta"] == 1


def test_page_understanding_builds_semantic_search_model():
    model = PageUnderstandingEngine().build_page_model(_google_serp_context())
    assert model.classification.page_type == "search_engine"
    assert model.adapter == "google_search"
    assert len(model.search_results) == 2
    assert any(element.kind == "search_result" for element in model.elements)
    assert model.telemetry["selector_candidate_count"] >= 2


def test_selector_intelligence_rejects_empty_and_scores_structural_lower():
    engine = SelectorIntelligenceEngine()
    assert engine.validate("") is False
    stable = engine.candidate_for("#APjFqb")
    structural = engine.candidate_for("div:nth-of-type(4) > center > input:nth-of-type(1)")
    assert stable.valid is True
    assert structural.valid is True
    assert stable.confidence > structural.confidence


def test_planner_context_exposes_explicit_result_urls_not_fake_selectors():
    artifact = build_browser_intelligence(_google_serp_context())
    planner_context = format_browser_intelligence_for_planner(artifact)
    assert planner_context["adapter"] == "google_search"
    first = planner_context["search_results"][0]
    assert first["rank"] == 1
    assert first["open_action"]["action_type"] == "open_new_tab"
    assert first["open_action"]["value"] == "https://browser-use.com/"


def test_action_verification_declares_new_tab_and_detects_missing_tab():
    artifact = build_browser_intelligence(_google_serp_context())
    state = artifact.browser_state
    verifier = ActionVerificationEngine()
    expectation = verifier.expectation_for(
        type("Action", (), {"action_type": "open_new_tab", "value": "https://playwright.dev/", "target_selector": None})(),
        state,
    )
    assert expectation.expected["tab_count_delta"] == 1
    outcome = verifier.verify_state_transition(
        action_type="open_new_tab",
        before=state,
        after=state,
        expected=expectation.expected,
    )
    assert outcome.verified is False
    assert outcome.false_success_prevented is True


def test_google_serp_invented_selector_is_repaired_to_open_new_tab_url():
    response = AnalyzeResponse(
        session_id="s1",
        analysis="Open the fifth relevant search result.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="open_fifth_result",
                action_type="click",  # type: ignore[arg-type]
                target_selector="div > div > div > ul > li:nth-of-type(5) > div:nth-of-type(1) > a",
                value=None,
                description="This action will open the fifth relevant search result in a new tab.",
                reasoning="The fifth result is needed for the comparison.",
                confidence=1.0,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )
    repaired = _postprocess_planner_response(
        response,
        page_context=_google_serp_context_with_five_results(),
    )
    assert repaired.outcome_kind == "act"
    assert repaired.suggested_actions[0].action_type == "open_new_tab"
    assert repaired.suggested_actions[0].value == "https://tool5.example/"


def test_google_home_navigation_is_repaired_to_direct_search_url():
    response = AnalyzeResponse(
        session_id="s1",
        analysis="Open Google Search.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="navigate_google",
                action_type="navigate",  # type: ignore[arg-type]
                target_selector="",
                value="https://www.google.com",
                description="Open Google Search.",
                reasoning="Search from Google.",
                confidence=1.0,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )
    repaired = _postprocess_planner_response(
        response,
        page_context=PageContext(
            url="chrome://newtab/",
            title="New Tab",
            metadata={},
            interactive_elements=[],
            content_blocks=[],
            headings=[],
            selected_text="",
            visible_text="",
            images=[],
        ),
        task="Open Google Search and search for: `best AI browser automation tools 2026`.",
    )
    assert repaired.suggested_actions[0].action_type == "navigate"
    assert repaired.suggested_actions[0].value == (
        "https://www.google.com/search?q=best+AI+browser+automation+tools+2026"
    )


def test_google_repeated_result_open_advances_to_next_unopened_url():
    response = AnalyzeResponse(
        session_id="s-repeat",
        analysis="Open the first relevant search result again.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="open_first_result_again",
                action_type="click",  # type: ignore[arg-type]
                target_selector="div > div > div > ul > li:nth-of-type(1) > a",
                value=None,
                description="Open the first relevant search result in a new tab.",
                reasoning="The first result is needed for the comparison.",
                confidence=1.0,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )
    repaired = _postprocess_planner_response(
        response,
        page_context=_google_serp_context_with_five_results(),
        task="Open Google Search and search for: `best AI browser automation tools 2026`. Open the top 5 relevant results.",
        prior_steps=[
            PriorStep(
                action_type="open_new_tab",
                description="Open organic Google result #1",
                value="https://tool1.example/",
                execution_result="success",
            )
        ],
    )

    assert repaired.suggested_actions[0].action_type == "open_new_tab"
    assert repaired.suggested_actions[0].value == "https://tool2.example/"


def test_google_navigation_after_opened_result_focuses_existing_serp_tab():
    response = AnalyzeResponse(
        session_id="s-focus",
        analysis="Navigate back to Google Search.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="navigate_google_again",
                action_type="navigate",  # type: ignore[arg-type]
                target_selector="",
                value="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
                description="Navigate to Google Search with the specified query.",
                reasoning="Return to Google to open the next result.",
                confidence=1.0,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )
    repaired = _postprocess_planner_response(
        response,
        page_context=PageContext(
            url="https://tool1.example/",
            title="Tool 1",
            metadata={},
            interactive_elements=[],
            content_blocks=[],
            headings=[],
            selected_text="",
            visible_text="",
            images=[],
        ),
        task="Open Google Search and search for: `best AI browser automation tools 2026`. Open the top 5 relevant results.",
        prior_steps=[
            PriorStep(
                action_type="open_new_tab",
                description="Open organic Google result #1",
                value="https://tool1.example/",
                execution_result="success",
            )
        ],
    )

    assert repaired.suggested_actions[0].action_type == "focus_existing_tab"
    assert repaired.suggested_actions[0].value == (
        "url:https://www.google.com/search?q=best+AI+browser+automation+tools+2026"
    )
