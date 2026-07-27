from __future__ import annotations

from dataclasses import replace

from app.core.config import settings
from app.execution_orchestrator.engine import ExecutionOrchestrator
from app.execution_orchestrator.models import PhaseState
from app.feature_flags import get_flag_state
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
    assert snapshot.progress_ledger.completed["open"] is True
    assert "open_new_tab" in snapshot.active_phase.forbidden_actions


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


def test_active_read_phase_rejects_more_open_tab_actions(monkeypatch):
    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    engine = ExecutionOrchestrator()
    snapshot = engine.build_snapshot(
        session_id="reject-open",
        task=TASK,
        page_context=_page("https://tool5.example/"),
        prior_steps=_opened_steps(5),
    )

    result = engine.postprocess_response(_planner_action("open_new_tab", value="https://tool1.example/"), snapshot)

    assert result.outcome_kind == "replan"
    assert result.suggested_actions == []
    assert result.replan is not None
    assert "Current phase: READ" in result.replan.reason


def test_active_read_phase_allows_focus_tab(monkeypatch):
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
    assert result.suggested_actions[0].action_type == "focus_existing_tab"


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
