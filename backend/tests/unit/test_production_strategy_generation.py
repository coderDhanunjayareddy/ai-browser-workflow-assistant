from app.orchestrator.strategy_generation import (
    consume_strategy_prior_steps,
    has_pending_strategy_context,
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
        session_id="sg-test",
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


def report_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="sg-test",
        analysis="Total found.",
        outcome_kind="report",
        suggested_actions=[],
        report=ReportOutcome(answer="$42.00", claim="The total is visible."),
        sgv_verified=False,
    )


def test_no_convergence_produces_no_strategy_context():
    session_id = "sg-no-convergence"
    reset_strategy_generation(session_id)

    prepared = prepare_strategy_context_if_stalled(
        session_id=session_id,
        goal_convergence=False,
        task="Find the next result",
        page_context=make_page_context(),
        planner_response=act_response(),
    )

    assert prepared is False
    assert has_pending_strategy_context(session_id) is False
    assert consume_strategy_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=make_page_context(),
    ) == []


def test_convergence_generates_strategy_context_for_next_planner_turn():
    session_id = "sg-convergence"
    reset_strategy_generation(session_id)

    prepared = prepare_strategy_context_if_stalled(
        session_id=session_id,
        goal_convergence=True,
        task="Find the next result",
        page_context=make_page_context(),
        planner_response=act_response(),
        convergence_reason="semantic evidence unchanged",
    )
    steps = consume_strategy_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=make_page_context(),
    )

    assert prepared is True
    assert len(steps) == 1
    assert steps[0].action_type == "replan"
    assert steps[0].description == "Strategy Generation: previous strategy stalled"
    assert "STRATEGY GENERATION CONTEXT" in (steps[0].page_analysis or "")
    assert "Expected semantic goal: Find the next result" in (steps[0].page_analysis or "")
    assert "Avoid next:" in (steps[0].page_analysis or "")
    assert has_pending_strategy_context(session_id) is False


def test_planner_response_is_not_modified():
    session_id = "sg-preserve-response"
    reset_strategy_generation(session_id)
    response = act_response()
    original = response.model_dump()

    prepare_strategy_context_if_stalled(
        session_id=session_id,
        goal_convergence=True,
        task="Find the next result",
        page_context=make_page_context(),
        planner_response=response,
    )

    assert response.model_dump() == original


def test_unverified_report_keeps_sgv_state_and_includes_validation_miss():
    session_id = "sg-report"
    reset_strategy_generation(session_id)
    response = report_response()

    prepare_strategy_context_if_stalled(
        session_id=session_id,
        goal_convergence=True,
        task="Tell me the total",
        page_context=make_page_context(visible_text="Loading invoice"),
        planner_response=response,
    )
    steps = consume_strategy_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=make_page_context(visible_text="Loading invoice"),
    )

    assert response.outcome_kind == "report"
    assert response.sgv_verified is False
    assert response.suggested_actions == []
    assert "Validation still missing: report answer '$42.00' not verified" in (
        steps[0].page_analysis or ""
    )


def test_duplicate_strategy_context_is_not_emitted_twice():
    session_id = "sg-duplicate"
    reset_strategy_generation(session_id)
    ctx = make_page_context()
    response = act_response()

    first = prepare_strategy_context_if_stalled(
        session_id=session_id,
        goal_convergence=True,
        task="Find the next result",
        page_context=ctx,
        planner_response=response,
    )
    consume_strategy_prior_steps(
        session_id=session_id,
        prior_steps=[],
        page_context=ctx,
    )
    second = prepare_strategy_context_if_stalled(
        session_id=session_id,
        goal_convergence=True,
        task="Find the next result",
        page_context=ctx,
        planner_response=response,
    )

    assert first is True
    assert second is False
    assert has_pending_strategy_context(session_id) is False
