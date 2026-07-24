from __future__ import annotations

from app.core.config import settings
from app.execution_continuity.engine import ExecutionContinuityEngine
from app.feature_flags import get_flag_state
from app.schemas.request import PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction


def _page(url: str = "https://example.test/search") -> PageContext:
    return PageContext(
        url=url,
        title="Example",
        metadata={},
        interactive_elements=[],
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="",
        images=[],
    )


def _step(action_type: str, description: str, *, value: str | None = None, result: str = "success") -> PriorStep:
    return PriorStep(
        action_type=action_type,
        description=description,
        target_selector="#target",
        value=value,
        execution_result=result,
        page_url="https://example.test/search",
        page_title="Example",
    )


def test_v47_feature_flag_defaults_to_shadow():
    assert get_flag_state("V47_EXECUTION_CONTINUITY").value == "shadow"


def test_shadow_mode_records_snapshot_without_enriching_planner_context(monkeypatch):
    monkeypatch.setattr(settings, "v47_execution_continuity", "shadow")
    engine = ExecutionContinuityEngine()

    snapshot = engine.observe(
        session_id="s1",
        task="Open a site. Extract pricing. Return final answer.",
        page_context=_page(),
        prior_steps=[_step("navigate", "Open a site", value="https://example.test/search")],
    )

    assert snapshot is not None
    assert snapshot.session_id == "s1"
    assert snapshot.mission.progress_percent > 0
    assert engine.enrich_context({"active_goal": "x"}, snapshot) == {"active_goal": "x"}


def test_active_mode_adds_compact_execution_continuity_context(monkeypatch):
    monkeypatch.setattr(settings, "v47_execution_continuity", "active")
    engine = ExecutionContinuityEngine()

    snapshot = engine.observe(
        session_id="s2",
        task="Open a site. Extract pricing. Return final answer.",
        page_context=_page(),
        prior_steps=[_step("navigate", "Open a site", value="https://example.test/search")],
    )
    enriched = engine.enrich_context({"active_goal": "x"}, snapshot)

    assert "execution_continuity" in enriched
    assert enriched["execution_continuity"]["mission_progress"]["current_objective"]
    assert enriched["execution_continuity"]["browser_state"]["current_url"] == "https://example.test/search"


def test_loop_detection_identifies_repeated_actions(monkeypatch):
    monkeypatch.setattr(settings, "v47_execution_continuity", "shadow")
    engine = ExecutionContinuityEngine()

    snapshot = engine.observe(
        session_id="s3",
        task="Click the next button. Return final answer.",
        page_context=_page(),
        prior_steps=[
            _step("click", "Click the next button", result="Element not found"),
            _step("click", "Click the next button", result="Element not found"),
            _step("click", "Click the next button", result="Element not found"),
        ],
    )

    assert snapshot is not None
    assert snapshot.progress_validation.loop_signal.kind == "repeat_action"
    assert snapshot.progress_validation.recommendation == "replan"


def test_active_mode_converts_repeated_planner_action_to_replan(monkeypatch):
    monkeypatch.setattr(settings, "v47_execution_continuity", "active")
    engine = ExecutionContinuityEngine()
    snapshot = engine.observe(
        session_id="s4",
        task="Click the next button. Return final answer.",
        page_context=_page(),
        prior_steps=[
            _step("click", "Click the next button", result="Element not found"),
            _step("click", "Click the next button", result="Element not found"),
            _step("click", "Click the next button", result="Element not found"),
        ],
    )
    response = AnalyzeResponse(
        session_id="s4",
        analysis="Try clicking the same button again.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="click_next_again",
                action_type="click",  # type: ignore[arg-type]
                target_selector="#target",
                value=None,
                description="Click the next button",
                reasoning="Retry the same action.",
                confidence=0.7,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )

    repaired = engine.postprocess_response(response, snapshot)

    assert repaired.outcome_kind == "replan"
    assert repaired.suggested_actions == []
    assert repaired.replan is not None
    assert "Next objective" in repaired.replan.reason
