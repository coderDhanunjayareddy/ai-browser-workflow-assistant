from app.orchestrator.seat_eligibility import (
    enforce_seat_action_eligibility, observed_seat_eligibility_response,
)
from app.orchestrator.workflow_orchestrator import _enforce_authoritative_semantic_grounding
from app.schemas.request import InteractiveElement, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction


TASK = "Find a bus for one adult on 20 October 2026 and proceed as far as possible."


def seat(number: str, price: int, *, berth: str = "unreserved", selected: bool = False):
    state = "selected" if selected else "unselected"
    name = (f"Seat number {number}, lower deck, seat type seater, berth {berth}, "
            f"price {price} rupees, availability available, currently {state}. "
            f"Press space or enter to {'unselect' if selected else 'select'} this seat.")
    return InteractiveElement(type="div", role="button", text=f"₹{price}",
                              selector=f"#{number}", visible=True,
                              accessibility_name=name, aria_label=name)


def page(*controls):
    return PageContext(url="https://example.test/results?onward=20-Oct-2026",
                       title="Bus seats", selected_text="", visible_text="",
                       interactive_elements=list(controls))


def test_unknown_gender_chooses_lowest_priced_unreserved_seat_and_grounds_it():
    observed = page(seat("12B", 666, berth="reserved for male"),
                    seat("1C", 760), seat("2B", 808))
    result = observed_seat_eligibility_response(
        session_id="seat", task=TASK, page_context=observed, prior_steps=[],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#1C"
    grounded = _enforce_authoritative_semantic_grounding(
        session_id="seat", result=result, page_context=observed,
    )
    assert grounded.outcome_kind == "act"
    assert grounded.suggested_actions[0].target_selector == "#1C"


def test_ineligible_selected_seat_is_removed_before_another_is_chosen():
    observed = page(seat("12B", 666, berth="reserved for male", selected=True), seat("1C", 760))
    result = observed_seat_eligibility_response(
        session_id="seat", task=TASK, page_context=observed, prior_steps=[],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#12B"
    assert result.suggested_actions[0].description.startswith("Deselect observed seat")


def test_explicit_matching_gender_can_use_restricted_seat():
    observed = page(seat("12B", 666, berth="reserved for male"), seat("1C", 760))
    result = observed_seat_eligibility_response(
        session_id="seat", task="Book for one male passenger", page_context=observed,
        prior_steps=[],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#12B"


def test_selection_is_not_repeated_when_its_postcondition_is_missing():
    observed = page(seat("1C", 760), seat("2B", 808))
    result = observed_seat_eligibility_response(
        session_id="seat", task=TASK, page_context=observed,
        prior_steps=[PriorStep(action_type="click", target_selector="#1C", value=None,
                              description="Select observed eligible seat 1C priced 760",
                              execution_result="Execution: success", page_analysis="",
                              page_url=observed.url)],
    )
    assert result is not None
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []


def test_planner_click_on_unproven_restricted_seat_is_blocked():
    observed = page(seat("12B", 666, berth="reserved for male"))
    result = AnalyzeResponse(session_id="seat", outcome_kind="act", analysis="",
                             suggested_actions=[SuggestedAction(
                                 action_id="pick", action_type="click", target_selector="#12B",
                                 value=None, description="Choose seat 12B", reasoning="",
                                 confidence=0.9, safety_level="safe",
                             )])
    guarded = enforce_seat_action_eligibility(task=TASK, page_context=observed, result=result)
    assert guarded.outcome_kind == "ask"
    assert guarded.suggested_actions == []
