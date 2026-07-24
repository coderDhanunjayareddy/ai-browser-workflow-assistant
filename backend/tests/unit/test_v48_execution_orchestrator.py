from __future__ import annotations

from app.core.config import settings
from app.execution_orchestrator.engine import ExecutionOrchestrator
from app.feature_flags import get_flag_state
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


def _planner_action(action_type: str) -> AnalyzeResponse:
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
                value="https://tool6.example/" if action_type == "open_new_tab" else None,
                description="Open another result",
                reasoning="Planner wants another browser action.",
                confidence=0.8,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
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

    result = engine.postprocess_response(_planner_action("open_new_tab"), snapshot)

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
