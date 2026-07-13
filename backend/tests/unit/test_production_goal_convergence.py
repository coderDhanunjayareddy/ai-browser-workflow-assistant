from app.orchestrator.goal_convergence import (
    assess_goal_convergence,
    reset_goal_convergence,
    semantic_signature,
)
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, ReportOutcome, SuggestedAction


def make_page_context(
    *,
    visible_text: str = "Search",
    element_state: dict | None = None,
    input_type: str | None = None,
) -> PageContext:
    return PageContext(
        url="https://example.test",
        title="Example",
        metadata={},
        interactive_elements=[
            InteractiveElement(
                type="input",
                text="",
                selector="#q",
                visible=True,
                input_type=input_type,
                placeholder="Search",
                role="textbox",
                state=element_state or {},
            )
        ],
        content_blocks=[ContentBlock(text="Static block", selector=".block")],
        headings=["Example"],
        selected_text="",
        visible_text=visible_text,
        images=[],
    )


def act_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="gc-test",
        analysis="Click search.",
        outcome_kind="act",
        suggested_actions=[
            SuggestedAction(
                action_id="a1",
                action_type="click",
                target_selector="#q",
                value=None,
                description="Click search",
                reasoning="Continue workflow",
                confidence=0.9,
                safety_level="safe",
            )
        ],
    )


def report_response(*, verified: bool) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="gc-test",
        analysis="Total found.",
        outcome_kind="report",
        suggested_actions=[],
        report=ReportOutcome(answer="$42.00", claim="The total is visible."),
        sgv_verified=verified,
    )


def test_semantic_progress_keeps_convergence_false():
    session_id = "gc-progress"
    reset_goal_convergence(session_id)

    first = assess_goal_convergence(
        session_id=session_id,
        page_context=make_page_context(visible_text="Search"),
        planner_response=act_response(),
    )
    second = assess_goal_convergence(
        session_id=session_id,
        page_context=make_page_context(visible_text="Results loaded"),
        planner_response=act_response(),
    )

    assert first.goal_convergence is False
    assert second.goal_convergence is False


def test_identical_semantic_state_sets_convergence_true():
    session_id = "gc-stalled"
    reset_goal_convergence(session_id)
    ctx = make_page_context(visible_text="Still loading")

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


def test_changing_form_state_prevents_convergence():
    session_id = "gc-form"
    reset_goal_convergence(session_id)

    empty = assess_goal_convergence(
        session_id=session_id,
        page_context=make_page_context(element_state={"value": ""}),
        planner_response=act_response(),
    )
    filled = assess_goal_convergence(
        session_id=session_id,
        page_context=make_page_context(element_state={"value": "camera"}),
        planner_response=act_response(),
    )

    assert empty.goal_convergence is False
    assert filled.goal_convergence is False


def test_password_signature_tracks_filled_state_without_raw_value():
    empty = semantic_signature(make_page_context(
        input_type="password",
        element_state={"value": ""},
    ))
    filled_one = semantic_signature(make_page_context(
        input_type="password",
        element_state={"value": "secret-one"},
    ))
    filled_two = semantic_signature(make_page_context(
        input_type="password",
        element_state={"value": "secret-two"},
    ))

    assert empty != filled_one
    assert filled_one == filled_two


def test_report_verification_resets_convergence_and_remains_unchanged():
    session_id = "gc-report"
    reset_goal_convergence(session_id)
    ctx = make_page_context(visible_text="Total $42.00")

    assert assess_goal_convergence(
        session_id=session_id,
        page_context=ctx,
        planner_response=report_response(verified=False),
    ).goal_convergence is False

    verified = report_response(verified=True)
    assert assess_goal_convergence(
        session_id=session_id,
        page_context=ctx,
        planner_response=verified,
    ).goal_convergence is False

    assert verified.outcome_kind == "report"
    assert verified.suggested_actions == []
    assert verified.report and verified.report.answer == "$42.00"


def test_planner_response_fields_are_not_modified():
    session_id = "gc-preserve"
    reset_goal_convergence(session_id)
    response = act_response()
    original_action = response.suggested_actions[0].model_dump()

    assess_goal_convergence(
        session_id=session_id,
        page_context=make_page_context(),
        planner_response=response,
    )

    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].model_dump() == original_action
    assert response.report is None
    assert response.replan is None
