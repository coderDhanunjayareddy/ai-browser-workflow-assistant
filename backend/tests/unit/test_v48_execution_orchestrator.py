from __future__ import annotations

from dataclasses import replace

from app.core.config import settings
from app.execution_orchestrator.artifact_registry import build_artifacts
from app.execution_orchestrator.budgets import build_budgets
from app.execution_orchestrator.engine import ExecutionOrchestrator
from app.execution_orchestrator.models import PhaseState
from app.feature_flags import get_flag_state
from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective
from app.intent_providers.browser_intelligence_executor import execute as collect_search_results
from app.runtime_state_manager.entity_binding import register_entity
from app.schemas.request import PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction


TASK = """
Open Google Search and search for: best AI browser automation tools 2026.
From the first page of results:
1. Open the top 5 relevant results in new tabs.
2. Read each page.
3. Extract Tool, Purpose, Pricing, Limitation, URL.
4. Produce a comparison table.
"""


def _page(url: str = "https://example.test/current") -> PageContext:
    return PageContext(
        url=url,
        title="Current Page",
        metadata={},
        interactive_elements=[],
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="",
        images=[],
    )


def _opened_steps(count: int) -> list[PriorStep]:
    return [
        PriorStep(
            action_type="open_new_tab",
            description=f"Open result {index}",
            target_selector="",
            value=f"https://tool{index}.example/",
            execution_result="success",
            page_url="https://search.example/results",
            page_title="Search Results",
        )
        for index in range(1, count + 1)
    ]


def _collected_steps(count: int) -> list[PriorStep]:
    return [
        PriorStep(
            action_type="click",
            description=f"Collect candidate result {index}",
            target_selector="",
            value=f"https://tool{index}.example/",
            execution_result="success",
            page_url="https://search.example/results",
            page_title="Search Results",
        )
        for index in range(1, count + 1)
    ]


def _planner_action(action_type: str, *, value: str | None = None) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="v48",
        analysis="Continue opening another result.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="candidate",
                action_type=action_type,  # type: ignore[arg-type]
                target_selector="",
                value=value if value is not None else ("https://tool6.example/" if action_type == "open_new_tab" else None),
                description="Open another result",
                reasoning="Planner wants another browser action.",
                confidence=0.8,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )


def _wait_action() -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="v48",
        analysis="Wait for deterministic backend work.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="wait",
                action_type="wait",  # type: ignore[arg-type]
                target_selector="window",
                value="1000",
                description="Wait",
                reasoning="Planner wants to wait.",
                confidence=0.7,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )


def _register_results(session_id: str, count: int = 5) -> None:
    for index in range(1, count + 1):
        register_entity(
            session_id,
            entity_type="search_result",
            source_layer="browser_intelligence",
            title=f"Tool {index}",
            canonical_url=f"https://tool{index}.example/",
            confidence=0.92,
            metadata={"rank": str(index)},
        )


def _collect_directive() -> IntentDispatchDirective:
    return IntentDispatchDirective(
        mission_id="collect-to-open",
        intent="collect_search_results",
        owner="browser_intelligence",
        capability="serp_collection",
        dispatch_target="browser_intelligence",
        reason="Collect observed SERP results.",
    )


def test_v48_flag_can_run_in_shadow(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "shadow")
    assert get_flag_state("V48_EXECUTION_ORCHESTRATOR").value == "shadow"


def test_shadow_records_phase_state_without_context_enrichment(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "shadow")
    engine = ExecutionOrchestrator()

    snapshot = engine.build_snapshot(
        session_id="shadow",
        task=TASK,
        page_context=_page(),
        prior_steps=_opened_steps(2),
    )

    assert snapshot is not None
    assert snapshot.progress_ledger.current_counts["opened_pages"] == 2
    assert engine.enrich_context({"active_goal": "x"}, snapshot) == {"active_goal": "x"}


def test_interactive_open_phase_allows_direct_app_navigation(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="wa-open",
        task="Open WhatsApp Web and detect whether login is required.",
        page_context=_page("https://assistant.local/sidepanel"),
        prior_steps=[],
    )

    assert snapshot is not None
    assert snapshot.workflow_category == "interactive_browser_task"
    assert snapshot.active_phase.name == "OPEN"
    assert "navigate" in snapshot.active_phase.allowed_actions
    assert "navigate" not in snapshot.active_phase.forbidden_actions

    planner_response = _planner_action("navigate", value="")
    planner_response.suggested_actions[0].description = "Open WhatsApp Web"
    result = engine.postprocess_response(planner_response, snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value == "https://web.whatsapp.com/"


def test_research_open_phase_keeps_direct_navigation_forbidden(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    snapshot = ExecutionOrchestrator().build_snapshot(
        session_id="research-open-contract",
        task=TASK,
        page_context=_page("https://www.google.com/search?q=browser+automation"),
        prior_steps=[],
    )

    assert snapshot is not None
    assert snapshot.workflow_category == "multi_page_research"
    open_phase = next(phase for phase in snapshot.phases if phase.name == "OPEN")
    assert "navigate" not in open_phase.allowed_actions
    assert "navigate" in open_phase.forbidden_actions


def test_multi_entity_product_and_tool_tasks_preserve_requested_open_count(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    tasks = (
        "Open the official websites of 3 AI code assistant products from search results. For each product capture pricing.",
        "Pick 3 different tools and for each one find the official documentation page.",
    )

    for index, task in enumerate(tasks):
        snapshot = ExecutionOrchestrator().build_snapshot(
            session_id=f"multi-entity-target-{index}",
            task=task,
            page_context=_page("https://www.google.com/search?q=tools"),
            prior_steps=[],
        )

        assert snapshot is not None
        assert snapshot.progress_ledger.target_counts["opened_pages"] == 3


def test_prepositioned_fixture_pages_advance_to_interaction_phase(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    cases = (
        (
            'Log in with username "tester" and password "secret123", then confirm the welcome message appears',
            "http://127.0.0.1:5051/login",
            "fill",
        ),
        (
            "Navigate to page 2 of the paged list and confirm page 2 items appear",
            "http://127.0.0.1:5051/pagination",
            "click",
        ),
        (
            "Open the settings modal, then save the setting",
            "http://127.0.0.1:5051/modal",
            "click",
        ),
        (
            'Search for "fastapi" repositories on GitHub and confirm repositories appear in results',
            "https://github.com/search?type=repositories",
            "fill",
        ),
    )

    for index, (task, url, expected_action) in enumerate(cases):
        snapshot = ExecutionOrchestrator().build_snapshot(
            session_id=f"fixture-reconcile-{index}",
            task=task,
            page_context=_page(url),
            prior_steps=[],
        )

        assert snapshot is not None
        assert snapshot.workflow_category == "interactive_browser_task"
        assert snapshot.artifacts.opened_pages == [url]
        assert snapshot.active_phase.name == "VALIDATE"
        assert expected_action in snapshot.active_phase.allowed_actions


def test_prepositioned_single_page_extraction_advances_to_read() -> None:
    url = "https://github.com/torvalds/linux/pull/1"
    snapshot = ExecutionOrchestrator().build_snapshot(
        session_id="single-page-read",
        task='Open pull request #1 in "torvalds/linux" and extract the author name and the first comment',
        page_context=_page(url),
        prior_steps=[],
    )

    assert snapshot is not None
    assert snapshot.workflow_category == "interactive_browser_task"
    assert snapshot.artifacts.opened_pages == [url]
    assert snapshot.active_phase.name == "READ"


def test_multi_source_search_remains_multi_page_research() -> None:
    snapshot = ExecutionOrchestrator().build_snapshot(
        session_id="multi-source-search",
        task=TASK,
        page_context=_page("https://www.google.com/search?q=browser+automation"),
        prior_steps=[],
    )

    assert snapshot is not None
    assert snapshot.workflow_category == "multi_page_research"


def test_interactive_browser_task_stays_in_validate_for_browser_interaction(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="interactive-whatsapp",
        task="Open WhatsApp Web and send a hii message to Rahul.",
        page_context=_page("https://web.whatsapp.com/"),
        prior_steps=[
            PriorStep(
                action_type="navigate",
                description="Reach target state",
                target_selector="",
                value="https://web.whatsapp.com/",
                execution_result="Navigating to: https://web.whatsapp.com/",
                page_url="https://web.whatsapp.com/",
                page_title="WhatsApp",
                browser_evidence={"page_url": "https://web.whatsapp.com/", "page_title": "WhatsApp"},
            ),
            PriorStep(
                action_type="focus_existing_tab",
                description="Focus opened source for read phase",
                target_selector="",
                value="url:https://web.whatsapp.com/",
                execution_result="success",
                page_url="https://web.whatsapp.com/",
                page_title="WhatsApp",
            ),
        ],
    )

    assert snapshot.workflow_category == "interactive_browser_task"
    assert snapshot.active_phase.name == "VALIDATE"
    assert "fill" in snapshot.active_phase.allowed_actions

    result = engine.postprocess_response(_planner_action("fill", value="Rahul"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "fill"


def test_media_playback_stays_in_validate_until_playback_is_verified(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="interactive-youtube-playback",
        task="Play Telugu music on YouTube",
        page_context=_page("https://www.youtube.com/"),
        prior_steps=[
            PriorStep(
                action_type="navigate",
                description="Open resolved YouTube destination",
                target_selector="",
                value="https://www.youtube.com/",
                execution_result="success",
                page_url="https://www.youtube.com/",
                page_title="YouTube",
            ),
        ],
    )

    assert snapshot.workflow_category == "interactive_browser_task"
    assert snapshot.active_phase.name == "VALIDATE"
    assert {"fill", "click", "wait", "media_control"}.issubset(snapshot.active_phase.allowed_actions)


def test_after_required_pages_opened_active_phase_becomes_read(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "shadow")
    engine = ExecutionOrchestrator()

    snapshot = engine.build_snapshot(
        session_id="read-phase",
        task=TASK,
        page_context=_page("https://tool5.example/"),
        prior_steps=_opened_steps(5),
    )

    assert snapshot is not None
    assert snapshot.active_phase.name == "READ"


def test_backend_read_page_receipts_complete_read_phase(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "shadow")
    engine = ExecutionOrchestrator()
    prior_steps = _opened_steps(5) + [
        PriorStep(
            action_type="read_page",
            description=f"Read opened source page: https://tool{index}.example/",
            target_selector="",
            value="",
            execution_result="Intent execution queue completed.\nKnowledge Extraction executed read_page.",
            page_url=f"https://tool{index}.example/",
            page_title=f"Tool {index}",
        )
        for index in range(1, 6)
    ]

    snapshot = engine.build_snapshot(
        session_id="read-page-receipts",
        task=TASK,
        page_context=_page("https://tool5.example/"),
        prior_steps=prior_steps,
    )

    assert snapshot is not None
    assert snapshot.progress_ledger.completed["read"] is True
    assert snapshot.active_phase.name == "EXTRACT"


def test_backend_read_page_receipts_do_not_consume_retry_budget():
    prior_steps = [
        PriorStep(
            action_type="read_page",
            description=f"Read opened source page: https://tool{index}.example/",
            target_selector="",
            value="",
            execution_result="Intent execution queue completed.\nKnowledge Extraction executed read_page.",
            page_url=f"https://tool{index}.example/",
            page_title=f"Tool {index}",
        )
        for index in range(1, 4)
    ]

    artifacts = build_artifacts(_page("https://tool3.example/"), prior_steps)
    budgets = build_budgets(prior_steps, artifacts)

    assert budgets.consumed["retries"] == 0
    assert "max_retries" not in budgets.exhausted


def test_collected_search_results_feed_open_phase_continuation(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "collect-to-open"
    collect_search_results(
        ExecutionContext(
            mission_id=session_id,
            task=TASK,
            page_context={"url": "https://www.google.com/search?q=best+AI+browser+automation+tools+2026"},
            browser_intelligence={
                "page_model": {
                    "search_results": [
                        {"rank": 1, "title": "Browser automation Tool 1", "url": "https://tool1.example/"},
                        {"rank": 2, "title": "Browser automation Tool 2", "url": "https://tool2.example/"},
                        {"rank": 3, "title": "Browser automation Tool 3", "url": "https://tool3.example/"},
                        {"rank": 4, "title": "Browser automation Tool 4", "url": "https://tool4.example/"},
                        {"rank": 5, "title": "Browser automation Tool 5", "url": "https://tool5.example/"},
                    ]
                }
            },
        ),
        _collect_directive(),
    )
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.google.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[
            PriorStep(
                action_type="collect_search_results",
                description="Collect search result candidates from the SERP",
                target_selector="",
                value="",
                execution_result="success\nCollected 5 observed search results.",
                page_url="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
                page_title="Google Search",
            )
        ],
    )

    assert snapshot is not None
    response = AnalyzeResponse(
        session_id=session_id,
        analysis="Open the first result.",
        outcome_kind="act",
        suggested_actions=[
            SuggestedAction(
                action_id="open-1",
                action_type="open_new_tab",  # type: ignore[arg-type]
                target_selector="",
                value="https://tool1.example/",
                description="Open ranked result 1",
                reasoning="Open first source.",
                confidence=0.9,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )

    enriched = engine.postprocess_response(response, snapshot)

    assert enriched.execution_orchestrator is not None
    continuation_urls = [item.value for item in enriched.execution_orchestrator.continuation_actions]
    assert continuation_urls[:2] == ["https://tool2.example", "https://tool3.example"]
    assert snapshot.progress_ledger.completed["collect"] is True


def test_registered_search_entities_count_as_collected_items(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "registered-entities-collect-count"
    collect_search_results(
        ExecutionContext(
            mission_id=session_id,
            task=TASK,
            page_context={"url": "https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"},
            browser_intelligence={
                "page_model": {
                    "search_results": [
                        {"rank": index, "title": f"Browser automation Tool {index}", "url": f"https://tool{index}.example/"}
                        for index in range(1, 6)
                    ]
                }
            },
        ),
        _collect_directive(),
    )

    snapshot = ExecutionOrchestrator().build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[],
    )

    assert snapshot is not None
    assert snapshot.progress_ledger.current_counts["collected_items"] == 5
    assert snapshot.progress_ledger.completed["collect"] is True
    assert snapshot.active_phase.name == "OPEN"


def test_open_phase_recovers_invalid_scroll_by_opening_registered_entity(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "open-phase-scroll-recovery"
    collect_search_results(
        ExecutionContext(
            mission_id=session_id,
            task=TASK,
            page_context={"url": "https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"},
            browser_intelligence={
                "page_model": {
                    "search_results": [
                        {"rank": index, "title": f"Browser automation Tool {index}", "url": f"https://tool{index}.example/"}
                        for index in range(1, 6)
                    ]
                }
            },
        ),
        _collect_directive(),
    )
    snapshot = ExecutionOrchestrator().build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[],
    )

    result = ExecutionOrchestrator().postprocess_response(_planner_action("scroll", value="down"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value.rstrip("/") == "https://tool1.example"
    assert result.execution_orchestrator is not None
    assert [action.action_type for action in result.execution_orchestrator.continuation_actions] == [
        "open_new_tab",
        "open_new_tab",
        "open_new_tab",
        "open_new_tab",
    ]


def test_open_phase_recovers_wait_loop_by_opening_registered_entity(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "open-phase-wait-recovery"
    collect_search_results(
        ExecutionContext(
            mission_id=session_id,
            task=TASK,
            page_context={"url": "https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"},
            browser_intelligence={
                "page_model": {
                    "search_results": [
                        {"rank": index, "title": f"Browser automation Tool {index}", "url": f"https://tool{index}.example/"}
                        for index in range(1, 6)
                    ]
                }
            },
        ),
        _collect_directive(),
    )
    snapshot = ExecutionOrchestrator().build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[],
    )

    result = ExecutionOrchestrator().postprocess_response(_planner_action("wait", value="1000"), snapshot)

    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value.rstrip("/") == "https://tool1.example"
    assert snapshot.progress_ledger.completed["open"] is False
    assert snapshot.active_phase.name == "OPEN"


def test_active_mode_enriches_planner_with_phase_constraints(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="active",
        task=TASK,
        page_context=_page(),
        prior_steps=_opened_steps(5),
    )

    enriched = engine.enrich_context({"active_goal": "x"}, snapshot)

    assert "execution_orchestrator" in enriched
    assert enriched["planner_phase_constraints"]["current_phase"] == "READ"
    assert "open_new_tab" in enriched["planner_phase_constraints"]["forbidden_actions"]


def test_active_read_phase_recovers_more_open_tab_actions_by_reading_focused_source(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="reject-open",
        task=TASK,
        page_context=_page("https://tool5.example/"),
        prior_steps=_opened_steps(5),
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool1.example/"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "read_page"
    assert result.replan is None


def test_read_phase_routes_forbidden_navigation_on_opened_source_to_backend_page_read(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="read-focus-recovery",
        task=TASK,
        page_context=_page("https://tool1.example/"),
        prior_steps=_opened_steps(5),
    )

    result = engine.postprocess_response(
        _planner_action("navigate", value="https://www.google.com/search?q=more+sources"),
        snapshot,
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "read_page"
    assert result.replan is None


def test_source_cap_blocks_extra_open_and_advances_to_read_focus(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "source-cap-extra-open"
    _register_results(session_id, 8)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://search.example/results"),
        prior_steps=_opened_steps(5),
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool6.example/"), snapshot)

    assert snapshot.active_phase.name == "READ"
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "focus_existing_tab"
    assert result.suggested_actions[0].value == "url:https://tool1.example/"
    assert "source collection cap" in result.analysis


def test_source_cap_does_not_hijack_interactive_app_navigation(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    snapshot = ExecutionOrchestrator().build_snapshot(
        session_id="interactive-source-cap",
        task="Open the settings modal, then save the setting",
        page_context=_page("http://127.0.0.1:5051/modal"),
        prior_steps=[],
    )

    assert snapshot is not None
    proposed = _planner_action("click")
    proposed.suggested_actions[0].target_selector = "#open"
    result = ExecutionOrchestrator().postprocess_response(proposed, snapshot)

    assert result.suggested_actions[0].action_type == "click"
    assert result.suggested_actions[0].target_selector == "#open"


def test_source_cap_blocks_search_navigation_after_required_sources_opened(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "source-cap-search-navigation"
    _register_results(session_id, 8)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"),
        prior_steps=_opened_steps(5),
    )

    result = engine.postprocess_response(
        _planner_action("navigate", value="https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"),
        snapshot,
    )

    assert snapshot.active_phase.name == "READ"
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "focus_existing_tab"
    assert result.suggested_actions[0].value == "url:https://tool1.example/"
    assert "opened source target 5/5" in result.suggested_actions[0].reasoning


def test_read_phase_recovery_advances_after_focused_source(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="read-focus-advance",
        task=TASK,
        page_context=_page("https://tool1.example/"),
        prior_steps=[
            *_opened_steps(5),
            PriorStep(
                action_type="focus_existing_tab",
                description="Focus opened source for read phase",
                target_selector="",
                value="url:https://tool1.example/",
                execution_result="success",
                page_url="https://tool1.example/",
                page_title="Tool 1",
            ),
        ],
    )

    result = engine.postprocess_response(
        _planner_action("navigate", value="https://www.google.com/search?q=more+sources"),
        snapshot,
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "read_page"
    assert result.replan is None


def test_read_phase_routes_repeated_focus_on_opened_source_to_backend_page_read(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="read-repeated-focus",
        task=TASK,
        page_context=_page("https://tool1.example/"),
        prior_steps=[
            *_opened_steps(5),
            PriorStep(
                action_type="focus_existing_tab",
                description="Focus opened source for read phase",
                target_selector="",
                value="url:https://tool1.example/",
                execution_result="Focused tab: Tool 1",
                page_url="https://tool1.example/",
                page_title="Tool 1",
            ),
        ],
    )

    result = engine.postprocess_response(
        _planner_action("focus_existing_tab", value="url:https://tool1.example/"),
        snapshot,
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "read_page"


def test_read_phase_routes_wait_on_opened_source_to_backend_page_read(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="read-backend-handoff",
        task=TASK,
        page_context=_page("https://tool1.example/"),
        prior_steps=[
            *_opened_steps(5),
            PriorStep(
                action_type="focus_existing_tab",
                description="Focus opened source for read phase",
                target_selector="",
                value="url:https://tool1.example/",
                execution_result="success",
                page_url="https://tool1.example/",
                page_title="Tool 1",
            ),
        ],
    )

    result = engine.postprocess_response(_wait_action(), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "read_page"
    assert result.intent_dispatch.owner == "knowledge_extraction"


def test_active_collect_phase_collects_results_before_opening_tabs(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="collect-before-open",
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[],
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool1.example/"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "collect_search_results"
    assert result.intent_dispatch.owner == "browser_intelligence"


def test_active_collect_phase_allows_opening_partial_collected_candidate(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "collect-partial-open"
    _register_results(session_id, 1)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[],
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool1.example/"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value.startswith("entity:ent_")
    assert result.replan is None


def test_active_collect_partial_open_grounds_unregistered_url_to_registered_entity(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "collect-partial-open-grounded"
    _register_results(session_id, 1)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[],
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://unknown.example/"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value.startswith("entity:ent_")
    assert "registered search-result" in result.suggested_actions[0].reasoning


def test_active_collect_phase_allows_search_provider_recovery_navigation(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="collect-provider-recovery",
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026&rdr=1"),
        prior_steps=[],
    )

    result = engine.postprocess_response(
        _planner_action("navigate", value="https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"),
        snapshot,
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value == "https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"
    assert result.replan is None


def test_active_collect_phase_allows_search_provider_entrypoint_recovery(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="collect-provider-entrypoint-recovery",
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026&rdr=1"),
        prior_steps=[],
    )

    result = engine.postprocess_response(_planner_action("navigate", value="https://www.google.com/"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value == "https://www.google.com/"
    assert result.replan is None


def test_search_navigation_avoids_provider_that_already_challenged(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="avoid-challenged-search-provider",
        task=TASK,
        page_context=_page("https://www.usecarly.com/"),
        prior_steps=[
            PriorStep(
                action_type="navigate",
                description="Execute the research search query",
                target_selector="",
                value="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
                execution_result="Navigating to: https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
                page_url="https://www.google.com/sorry/index?continue=https%3A%2F%2Fwww.google.com%2Fsearch%3Fq%3Dbest%2BAI%2Bbrowser%2Bautomation%2Btools%2B2026",
                page_title="Google",
            )
        ],
    )

    result = engine.postprocess_response(
        _planner_action("navigate", value="https://www.google.com/search?q=best+AI+browser+automation+tools+2026"),
        snapshot,
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value == "https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"
    assert "rerouted" in result.suggested_actions[0].reasoning.lower()


def test_search_recovery_prefers_unopened_collected_source_over_provider_loop(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "avoid-search-provider-loop-with-collected-source"
    _register_results(session_id, 5)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.browserstack.com/"),
        prior_steps=[
            PriorStep(
                action_type="navigate",
                description="Execute the research search query",
                target_selector="",
                value="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
                execution_result="Navigating to: https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
                page_url="https://www.google.com/sorry/index?continue=https%3A%2F%2Fwww.google.com%2Fsearch%3Fq%3Dbest%2BAI%2Bbrowser%2Bautomation%2Btools%2B2026",
                page_title="Google",
            ),
            *_opened_steps(4),
        ],
    )

    result = engine.postprocess_response(
        _planner_action("navigate", value="https://www.google.com/search?q=best+AI+browser+automation+tools+2026"),
        snapshot,
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value.startswith("entity:ent_")
    assert "unopened collected source" in result.suggested_actions[0].reasoning


def test_active_collect_phase_converts_external_navigation_to_search_result_collection(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="collect-safe-web-navigation",
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026&rdr=1"),
        prior_steps=[],
    )

    result = engine.postprocess_response(_planner_action("navigate", value="https://example.com/source"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "collect_search_results"
    assert result.intent_dispatch.owner == "browser_intelligence"


def test_active_collect_phase_extracts_embedded_navigation_url(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="collect-embedded-navigation-url",
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026&rdr=1"),
        prior_steps=[],
    )
    response = _planner_action("navigate", value="Open https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026")

    result = engine.postprocess_response(response, snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value == "https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"
    assert result.replan is None


def test_active_read_phase_routes_focus_tab_on_opened_source_to_backend_page_read(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="allow-focus",
        task=TASK,
        page_context=_page("https://tool5.example/"),
        prior_steps=_opened_steps(5),
    )

    result = engine.postprocess_response(_planner_action("focus_existing_tab"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "read_page"


def test_active_read_phase_attaches_generalized_phase_queue(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="read-phase-queue",
        task=TASK,
        page_context=_page("https://search.example/results"),
        prior_steps=_opened_steps(5),
    )

    result = engine.postprocess_response(
        _planner_action("focus_existing_tab", value="url:https://tool1.example/"),
        snapshot,
    )

    assert result.outcome_kind == "act"
    assert result.execution_orchestrator is not None
    assert result.execution_orchestrator.active_phase == "READ"
    assert result.execution_orchestrator.should_replan is False
    assert [action.action_type for action in result.execution_orchestrator.continuation_actions] == [
        "focus_existing_tab",
        "focus_existing_tab",
        "focus_existing_tab",
        "focus_existing_tab",
    ]
    assert [action.value for action in result.execution_orchestrator.continuation_actions] == [
        "url:https://tool2.example",
        "url:https://tool3.example",
        "url:https://tool4.example",
        "url:https://tool5.example",
    ]


def test_active_open_phase_attaches_orchestrator_continuation_queue(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "phase-queue-open"
    _register_results(session_id, 5)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://search.example/results"),
        prior_steps=_collected_steps(5),
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool1.example/"), snapshot)

    assert result.outcome_kind == "act"
    assert result.execution_orchestrator is not None
    assert result.execution_orchestrator.active_phase == "OPEN"
    assert result.execution_orchestrator.should_replan is False
    assert [action.value for action in result.execution_orchestrator.continuation_actions] == [
        "https://tool2.example",
        "https://tool3.example",
        "https://tool4.example",
        "https://tool5.example",
    ]


def test_active_open_phase_filters_search_engine_internal_pages(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "phase-queue-filter-internal-serp"
    register_entity(
        session_id,
        entity_type="semantic_element",
        source_layer="browser_intelligence",
        title="Google challenge",
        canonical_url="https://www.google.com/sorry/index?continue=https%3A%2F%2Fwww.google.com%2Fsearch%3Fq%3Dbrowser",
        confidence=0.99,
        metadata={"rank": "1"},
    )
    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Google internal search",
        canonical_url="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
        confidence=0.98,
        metadata={"rank": "2"},
    )
    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Tool 2",
        canonical_url="https://tool2.example/",
        confidence=0.92,
        metadata={"rank": "3"},
    )
    register_entity(
        session_id,
        entity_type="link",
        source_layer="browser_intelligence",
        title="Tool 3",
        canonical_url="https://tool3.example/",
        confidence=0.91,
        metadata={"rank": "4"},
    )
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://www.google.com/sorry/index"),
        prior_steps=_collected_steps(5),
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool1.example/"), snapshot)

    assert result.execution_orchestrator is not None
    assert [action.value for action in result.execution_orchestrator.continuation_actions] == [
        "https://tool2.example",
        "https://tool3.example",
    ]


def test_active_open_phase_skips_already_opened_entities(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "phase-queue-skip-opened"
    _register_results(session_id, 5)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://search.example/results"),
        prior_steps=[*_collected_steps(5), *_opened_steps(2)],
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool3.example/"), snapshot)

    assert result.execution_orchestrator is not None
    assert [action.value for action in result.execution_orchestrator.continuation_actions] == [
        "https://tool4.example",
        "https://tool5.example",
    ]


def test_open_phase_recovery_skips_already_opened_entity(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "open-recovery-skip-opened"
    _register_results(session_id, 5)
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://tool1.example/"),
        prior_steps=[*_collected_steps(5), *_opened_steps(1)],
    )

    result = engine.postprocess_response(_planner_action("wait"), snapshot)

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value == "https://tool2.example"


def test_open_phase_search_scroll_collects_more_results_instead_of_replan(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="open-search-scroll-collect",
        task=TASK,
        page_context=_page("https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"),
        prior_steps=[
            PriorStep(
                action_type="navigate",
                description="Search",
                target_selector="",
                value="https://www.bing.com/search?q=best+AI+browser+automation+tools+2026",
                execution_result="success",
                page_url="https://www.bing.com/search?q=best+AI+browser+automation+tools+2026",
                page_title="Search",
            ),
            *_opened_steps(1),
        ],
    )
    snapshot = replace(
        snapshot,
        active_phase=PhaseState(
            name="OPEN",
            status="active",
            objective="OPEN: reach 5 opened_pages; currently 1",
            allowed_actions=["open_new_tab", "focus_existing_tab", "switch_tab", "wait"],
            forbidden_actions=["navigate", "fill"],
        ),
    )

    result = engine.postprocess_response(_planner_action("scroll", value="down"), snapshot)

    assert result.outcome_kind == "act"
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "collect_search_results"
    assert result.suggested_actions == []


def test_active_open_phase_dedupes_duplicate_canonical_targets(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    session_id = "phase-queue-dedupe"
    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Tool 1 duplicate A",
        canonical_url="https://tool1.example/path/?b=2&a=1",
        confidence=0.93,
        metadata={"rank": "1"},
    )
    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Tool 1 duplicate B",
        canonical_url="https://TOOL1.example/path/?a=1&b=2",
        confidence=0.91,
        metadata={"rank": "2"},
    )
    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Tool 2",
        canonical_url="https://tool2.example/",
        confidence=0.92,
        metadata={"rank": "3"},
    )
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task=TASK,
        page_context=_page("https://search.example/results"),
        prior_steps=_collected_steps(5),
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://planner.example/"), snapshot)

    assert result.execution_orchestrator is not None
    assert [action.value for action in result.execution_orchestrator.continuation_actions] == [
        "https://tool1.example/path?b=2&a=1",
        "https://tool2.example",
    ]


def test_backend_owned_synthesize_phase_rejects_browser_wait(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="reject-synthesize-wait",
        task=TASK,
        page_context=_page("https://tool5.example/"),
        prior_steps=_opened_steps(5),
    )
    snapshot = replace(
        snapshot,
        active_phase=PhaseState(
            name="SYNTHESIZE",
            status="active",
            objective="Synthesize final answer from artifacts.",
            allowed_actions=[],
            forbidden_actions=["navigate", "open_new_tab", "click", "fill", "scroll", "wait"],
        ),
    )

    result = engine.postprocess_response(_wait_action(), snapshot)

    assert result.outcome_kind == "replan"
    assert result.suggested_actions == []
    assert "action wait is not allowed in phase SYNTHESIZE" in result.replan.reason


def test_backend_owned_report_phase_rejects_browser_wait(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="reject-report-wait",
        task=TASK,
        page_context=_page("https://tool5.example/"),
        prior_steps=_opened_steps(5),
    )
    snapshot = replace(
        snapshot,
        active_phase=PhaseState(
            name="REPORT",
            status="active",
            objective="Return the final user-facing output.",
            allowed_actions=[],
            forbidden_actions=["navigate", "open_new_tab", "click", "fill", "scroll", "wait"],
        ),
    )

    result = engine.postprocess_response(_wait_action(), snapshot)

    assert result.outcome_kind == "replan"
    assert result.suggested_actions == []
    assert "action wait is not allowed in phase REPORT" in result.replan.reason
