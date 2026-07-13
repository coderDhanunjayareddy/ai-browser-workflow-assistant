from app.orchestrator.goal_convergence import assess_goal_convergence, reset_goal_convergence
from app.orchestrator.planner_recovery import (
    consume_recovery_prior_steps,
    has_pending_planner_recovery,
    prepare_planner_recovery_if_strategy_context,
    reset_planner_recovery,
)
from app.orchestrator.strategy_generation import (
    consume_strategy_prior_steps,
    prepare_strategy_context_if_stalled,
    reset_strategy_generation,
)
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, ReportOutcome, SuggestedAction


def make_page_context(visible_text: str = "Search results unchanged") -> PageContext:
    return PageContext(
        url="https://example.test/search",
        title="Search",
        metadata={},
        interactive_elements=[
            InteractiveElement(
                type="button",
                text="Next",
                selector="#next",
                visible=True,
                role="button",
                state={},
            )
        ],
        content_blocks=[ContentBlock(text="No new results", selector=".results")],
        headings=["Search"],
        selected_text="",
        visible_text=visible_text,
        images=[],
    )


def act_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="pr-test",
        analysis="Click next.",
        outcome_kind="act",
        suggested_actions=[
            SuggestedAction(
                action_id="a1",
                action_type="click",
                target_selector="#next",
                value=None,
                description="Click next",
                reasoning="Continue workflow",
                confidence=0.9,
                safety_level="safe",
            )
        ],
    )


def report_response(*, verified: bool) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="pr-test",
        analysis="Total found.",
        outcome_kind="report",
        suggested_actions=[],
        report=ReportOutcome(answer="$42.00", claim="The total is visible."),
        sgv_verified=verified,
    )


def test_no_goal_convergence_creates_no_recovery_marker():
    session_id = "pr-inactive"
    reset_planner_recovery(session_id)

    prepared = prepare_planner_recovery_if_strategy_context(
        session_id=session_id,
        goal_convergence=False,
        strategy_context_prepared=True,
    )
    steps = consume_recovery_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=make_page_context(),
    )

    assert prepared is False
    assert steps == []
    assert has_pending_planner_recovery(session_id) is False


def test_no_strategy_context_creates_no_recovery_marker():
    session_id = "pr-no-strategy"
    reset_planner_recovery(session_id)

    prepared = prepare_planner_recovery_if_strategy_context(
        session_id=session_id,
        goal_convergence=True,
        strategy_context_prepared=False,
    )

    assert prepared is False
    assert has_pending_planner_recovery(session_id) is False


def test_recovery_marker_created_after_goal_convergence_and_strategy_generation():
    session_id = "pr-active"
    reset_strategy_generation(session_id)
    reset_planner_recovery(session_id)
    ctx = make_page_context()

    strategy_prepared = prepare_strategy_context_if_stalled(
        session_id=session_id,
        goal_convergence=True,
        task="Find the next result",
        page_context=ctx,
        planner_response=act_response(),
    )
    recovery_prepared = prepare_planner_recovery_if_strategy_context(
        session_id=session_id,
        goal_convergence=True,
        strategy_context_prepared=strategy_prepared,
    )
    strategy_steps = consume_strategy_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=ctx,
    )
    recovery_steps = consume_recovery_prior_steps(
        session_id=session_id,
        prior_steps=strategy_steps,
        page_context=ctx,
    )

    assert strategy_prepared is True
    assert recovery_prepared is True
    assert len(recovery_steps) == 2
    assert "STRATEGY GENERATION CONTEXT" in (recovery_steps[0].page_analysis or "")
    assert recovery_steps[1].description == "Planner Recovery: one-turn recovery planning"
    assert "PLANNER RECOVERY MODE" in (recovery_steps[1].page_analysis or "")


def test_recovery_marker_is_one_shot():
    session_id = "pr-one-shot"
    reset_planner_recovery(session_id)
    ctx = make_page_context()

    assert prepare_planner_recovery_if_strategy_context(
        session_id=session_id,
        goal_convergence=True,
        strategy_context_prepared=True,
    ) is True

    first = consume_recovery_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=ctx,
    )
    second = consume_recovery_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=ctx,
    )

    assert len(first) == 1
    assert "PLANNER RECOVERY MODE" in (first[0].page_analysis or "")
    assert second == []
    assert has_pending_planner_recovery(session_id) is False


def test_planner_response_is_not_modified_by_recovery():
    session_id = "pr-preserve"
    reset_planner_recovery(session_id)
    response = act_response()
    original = response.model_dump()

    prepare_planner_recovery_if_strategy_context(
        session_id=session_id,
        goal_convergence=True,
        strategy_context_prepared=True,
    )

    assert response.model_dump() == original
    assert response.outcome_kind == "act"
    assert response.report is None
    assert response.replan is None
    assert response.clarification_question is None


def test_verified_reports_remain_sgv_verified_and_do_not_create_actions():
    response = report_response(verified=True)

    prepare_planner_recovery_if_strategy_context(
        session_id="pr-sgv",
        goal_convergence=True,
        strategy_context_prepared=True,
    )

    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.suggested_actions == []
    assert response.report and response.report.answer == "$42.00"


def test_goal_convergence_detection_logic_is_unchanged():
    session_id = "pr-gc"
    reset_goal_convergence(session_id)
    ctx = make_page_context()

    first = assess_goal_convergence(
        session_id=session_id,
        page_context=ctx,
        planner_response=act_response(),
    )
    second = assess_goal_convergence(
        session_id=session_id,
        page_context=ctx,
        planner_response=act_response(),
    )

    assert first.goal_convergence is False
    assert second.goal_convergence is True
