from __future__ import annotations

from app.browser_intelligence import build_browser_intelligence
from app.browser_intelligence.action_verification import ActionVerificationEngine
from app.browser_intelligence.adapters import AdapterRegistry
from app.browser_intelligence.dynamic_dom import DynamicDomTracker
from app.browser_intelligence.memory import BrowserMemory
from app.browser_intelligence.page_understanding import PageUnderstandingEngine
from app.browser_intelligence.recovery import AdaptiveRecoveryEngine
from app.browser_intelligence.waits import IntelligentWaitingEngine
from app.capability_platform.browser_registry import get_browser_capability
from app.feature_flags import get_flag_state, v4_flag_snapshot
from app.schemas.request import ContentBlock, InteractiveElement, PageContext


def _context(url: str, title: str, elements: list[InteractiveElement], *, text: str = "") -> PageContext:
    return PageContext(
        url=url,
        title=title,
        metadata={},
        interactive_elements=elements,
        content_blocks=[ContentBlock(selector=element.selector, text=element.text, href=element.href) for element in elements],
        headings=[title],
        selected_text="",
        visible_text=text or " ".join(element.text for element in elements),
        images=[],
    )


def _button(label: str, selector: str, *, role: str = "button") -> InteractiveElement:
    return InteractiveElement(type="button", text=label, selector=selector, visible=True, role=role)


def test_v46_flags_default_to_shadow():
    flags = v4_flag_snapshot()
    assert flags["V46_DYNAMIC_DOM"] == "shadow"
    assert flags["V46_INTELLIGENT_WAIT"] == "shadow"
    assert flags["V46_BROWSER_MEMORY"] == "shadow"
    assert flags["V46_RECOVERY_ENGINE"] == "shadow"
    assert flags["V46_VISUAL_GROUNDING"] == "shadow"
    assert get_flag_state("V46_BROWSER_HEALTH").value == "shadow"


def test_v46_capability_registry_records_are_complete():
    dynamic = get_browser_capability("browser_intelligence.dynamic_dom")
    recovery = get_browser_capability("browser_intelligence.recovery.adaptive")
    health = get_browser_capability("browser_intelligence.health")
    assert dynamic is not None and dynamic.feature_flag == "V46_DYNAMIC_DOM"
    assert recovery is not None and recovery.maturity_level == 4
    assert health is not None and "browser_health_score" in health.metrics


def test_dynamic_dom_tracking_detects_react_rerender_semantic_change():
    engine = PageUnderstandingEngine()
    tracker = DynamicDomTracker()
    first = engine.build_page_model(_context("https://app.test", "Dashboard", [_button("Save", "#save")]))
    second = engine.build_page_model(_context("https://app.test", "Dashboard", [_button("Save", "#save"), _button("Export", "#export")]))
    assert tracker.track("react-rerender", first)[0].mutation_type == "initial_observation"
    mutations = tracker.track("react-rerender", second)
    assert mutations
    assert mutations[0].requires_refresh is True
    assert mutations[0].metadata["delta"]["button"] == 1


def test_intelligent_waits_wait_for_search_results_loaded():
    ctx = _context("https://www.google.com/search?q=tools", "Google Search", [], text="Search loading")
    model = PageUnderstandingEngine().build_page_model(ctx)
    state = PageUnderstandingEngine().build_browser_state(ctx, model)
    wait = IntelligentWaitingEngine().plan(model, state)
    assert wait.ready is False
    assert wait.wait_type in {"search_results_loaded", "spinner_disappears"}


def test_browser_memory_tracks_navigation_chain_and_recent_search_results():
    memory = BrowserMemory()
    engine = PageUnderstandingEngine()
    first = _context("https://www.google.com/search?q=x", "Google Search", [
        InteractiveElement(type="a", text="Playwright", selector='a[href="https://playwright.dev/"]', visible=True, href="https://playwright.dev/")
    ])
    second = _context("https://playwright.dev/", "Playwright", [_button("Docs", "#docs")], text="Documentation")
    first_model = engine.build_page_model(first)
    first_state = engine.build_browser_state(first, first_model)
    memory.remember("memory", first_model, first_state)
    second_model = engine.build_page_model(second)
    second_state = engine.build_browser_state(second, second_model)
    snapshot = memory.remember("memory", second_model, second_state)
    assert snapshot.navigation_chain[-2:] == ["https://www.google.com/search?q=x", "https://playwright.dev/"]
    assert snapshot.recent_search_results[0]["url"] == "https://playwright.dev/"


def test_adaptive_recovery_uses_semantic_text_match_before_replan():
    model = PageUnderstandingEngine().build_page_model(
        _context("https://app.test", "Settings", [_button("Save changes", 'button[aria-label="Save changes"]')])
    )
    decision = AdaptiveRecoveryEngine().recover(
        failed_selector="div:nth-of-type(8) > button:nth-of-type(2)",
        target_label="Save",
        page_model=model,
    )
    assert decision.recovered is True
    assert decision.selector == 'button[aria-label="Save changes"]'
    assert decision.strategy in {"stable_selector", "semantic_selector", "accessibility_selector", "text_matching", "similar_element_search"}


def test_adapter_switching_selects_requested_universal_adapters():
    registry = AdapterRegistry()
    cases = {
        "linkedin_jobs": _context("https://www.linkedin.com/jobs/search", "Jobs", []),
        "github": _context("https://github.com/openai/codex", "GitHub", []),
        "gmail": _context("https://mail.google.com/mail/u/0/#inbox", "Inbox", []),
        "outlook": _context("https://outlook.office.com/mail/", "Outlook", []),
        "notion": _context("https://www.notion.so/page", "Notion", []),
        "jira": _context("https://team.atlassian.net/jira/software/projects/ABC", "Jira", [], text="Issue Sprint"),
        "confluence": _context("https://team.atlassian.net/wiki/spaces/ABC", "Confluence", [], text="Confluence page"),
        "generic_data_table": _context("https://app.test/table", "Table", [
            InteractiveElement(type="div", text="Row 1", selector="#r1", visible=True, role="row"),
            InteractiveElement(type="div", text="Row 2", selector="#r2", visible=True, role="row"),
            InteractiveElement(type="div", text="Row 3", selector="#r3", visible=True, role="row"),
        ]),
    }
    for expected, ctx in cases.items():
        assert registry.select(ctx).name == expected


def test_visual_grounding_and_health_are_replay_compatible():
    artifact = build_browser_intelligence(
        _context("https://app.test/dashboard", "Dashboard", [_button("Export", "#export")], text="Dashboard metrics"),
        scope_id="visual-health",
    )
    assert artifact.visual_targets
    assert artifact.health is not None
    assert artifact.health.health_score > 0
    assert artifact.replay["visual_targets"][0]["target_id"]
    assert artifact.replay["health"]["browser_health_score"] if "browser_health_score" in artifact.replay["health"] else artifact.replay["health"]["health_score"]


def test_cross_validation_requires_multiple_signals_for_tab_creation_and_search_result():
    verifier = ActionVerificationEngine()
    tab = verifier.cross_validate(
        action_type="open_new_tab",
        signals={"tab_count_increased": True, "active_tab_url": "https://example.test", "new_tab_url": "https://example.test"},
    )
    result = verifier.cross_validate(
        action_type="search_result",
        signals={"adapter": "google_search", "title": "Example", "url": "https://example.test"},
    )
    weak = verifier.cross_validate(action_type="download", signals={"download_event": True})
    assert tab.verified is True
    assert result.verified is True
    assert weak.verified is False
