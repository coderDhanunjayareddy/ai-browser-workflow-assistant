from app.orchestrator.search_prerequisites import (
    enforce_observed_date_before_result, observed_date_prerequisite_response,
    observed_result_prerequisite_response, observed_route_prerequisite_response,
)
from app.schemas.request import ContentBlock, InteractiveElement, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction


def page(*controls, prices=False):
    return PageContext(
        url="https://example.test/results", title="Results", selected_text="", visible_text="",
        interactive_elements=list(controls),
        content_blocks=([ContentBlock(selector="#item-one", text="Option A $100"),
                         ContentBlock(selector="#item-two", text="Option B $120")] if prices else []),
    )


def control(selector="#departure", value="Wed, Oct 07, 2026"):
    return InteractiveElement(
        type="input", role="textbox", input_type="text", text="", selector=selector,
        visible=True, accessibility_name=value, state={"readonly": True, "value": value},
    )


def proposal(description, selector="#stale"):
    return AnalyzeResponse(session_id="date", analysis="", suggested_actions=[SuggestedAction(
        action_id="planned", action_type="click", target_selector=selector, value=None,
        description=description, reasoning="", confidence=0.9, safety_level="safe",
    )])


TASK = "Find a one-way trip from A to B on 20 October 2026 for one adult. Choose the cheapest available option."


def test_observed_route_form_fills_source_then_destination_without_site_selector_rule():
    observed = page(
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#srcinput", visible=True, state={}),
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#destinput", visible=True, state={}),
        InteractiveElement(type="button", role="button", text="Search buses", selector="#search",
                           visible=True, accessibility_name="Search buses"),
    )
    task = "Find a bus from Hyderabad to Bengaluru on 20 October 2026 for one adult."
    first = observed_route_prerequisite_response(session_id="route", task=task, page_context=observed)
    assert first is not None
    assert first.suggested_actions[0].action_type == "fill"
    assert first.suggested_actions[0].target_selector == "#srcinput"
    assert first.suggested_actions[0].value == "Hyderabad"
    observed.interactive_elements[0].state = {"value": "Hyderabad"}
    second = observed_route_prerequisite_response(session_id="route", task=task, page_context=observed)
    assert second is not None
    assert second.suggested_actions[0].target_selector == "#destinput"
    assert second.suggested_actions[0].value == "Bengaluru"
    observed.interactive_elements[1].state = {"value": "Bengaluru"}
    search = observed_route_prerequisite_response(session_id="route", task=task, page_context=observed)
    assert search is not None
    assert search.suggested_actions[0].target_selector == "#search"
    assert search.suggested_actions[0].action_type == "click"


def test_unlabelled_observed_route_field_passes_authoritative_grounding():
    from app.orchestrator.workflow_orchestrator import _enforce_authoritative_semantic_grounding

    observed = page(
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#srcinput", visible=True, state={}),
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#destinput", visible=True, state={}),
        InteractiveElement(type="button", role="button", text="Search", selector="#search",
                           visible=True, accessibility_name="Search"),
    )
    result = observed_route_prerequisite_response(session_id="route", task=TASK, page_context=observed)
    assert result is not None
    grounded = _enforce_authoritative_semantic_grounding(
        session_id="route", result=result, page_context=observed,
    )
    assert grounded.outcome_kind == "act"
    assert grounded.suggested_actions[0].target_selector == "#srcinput"


def test_route_autocomplete_selects_observed_city_before_next_field():
    observed = page(
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#srcinput", visible=True, state={"value": "Hyderabad"}),
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#destinput", visible=True, state={}),
        InteractiveElement(type="button", role="button", text="Search", selector="#search",
                           visible=True, accessibility_name="Search"),
        InteractiveElement(type="div", role="button", text="Hyderabad",
                           selector="#suggestion-0", visible=True,
                           accessibility_name="Hyderabad, ,"),
        InteractiveElement(type="div", role="button", text="Hyderabad",
                           selector="#suggestion-14", visible=True,
                           accessibility_name="Hyderabad, ,"),
    )
    filled = PriorStep(
        action_type="fill", target_selector="#srcinput", value="Hyderabad",
        description="Set requested origin in the uniquely observed route field",
        execution_result="CDP fill dispatched.\nExecution: success\nVerification: verified",
    )
    task = "Find a bus from Hyderabad to Bengaluru on 20 October 2026 for one adult."
    result = observed_route_prerequisite_response(
        session_id="route", task=task, page_context=observed, prior_steps=[filled],
    )
    assert result is not None
    assert result.suggested_actions[0].action_type == "click"
    assert result.suggested_actions[0].target_selector == "#suggestion-0"
    from app.orchestrator.workflow_orchestrator import _enforce_authoritative_semantic_grounding
    grounded = _enforce_authoritative_semantic_grounding(
        session_id="route", result=result, page_context=observed,
    )
    assert grounded.outcome_kind == "act"
    selected = PriorStep(
        action_type="click", target_selector="#suggestion-0", value=None,
        description="Use observed city suggestion for origin",
        execution_result="CDP click dispatched.\nExecution: success\nVerification: verified",
    )
    observed.interactive_elements = observed.interactive_elements[:3]
    result = observed_route_prerequisite_response(
        session_id="route", task=task, page_context=observed,
        prior_steps=[filled, selected],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#destinput"


def test_route_form_does_not_repeat_successful_fill_when_value_disappears():
    observed = page(
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#srcinput", visible=True, state={}),
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#destinput", visible=True, state={}),
        InteractiveElement(type="button", role="button", text="Search", selector="#search",
                           visible=True, accessibility_name="Search"),
    )
    filled = PriorStep(
        action_type="fill", target_selector="#srcinput", value="Hyderabad",
        description="Set requested origin in the uniquely observed route field",
        execution_result="CDP fill dispatched.\nExecution: success\nVerification: verified",
    )
    result = observed_route_prerequisite_response(
        session_id="route", task="Find a bus from Hyderabad to Bengaluru on 20 October 2026.",
        page_context=observed, prior_steps=[filled],
    )
    assert result is not None
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []


def test_route_form_does_not_guess_ambiguous_or_unidentified_fields():
    observed = page(
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#from", visible=True),
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#another-from", visible=True),
        InteractiveElement(type="input", input_type="text", role="combobox", text="",
                           selector="#to", visible=True),
        InteractiveElement(type="button", role="button", text="Search", selector="#search",
                           visible=True, accessibility_name="Search"),
    )
    assert observed_route_prerequisite_response(session_id="route", task=TASK, page_context=observed) is None


def test_stale_date_selector_is_replaced_by_uniquely_observed_current_control():
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control()), prior_steps=[],
        result=proposal("Click the departure date field to select the travel date"),
    )
    assert result.suggested_actions[0].target_selector == "#departure"
    assert result.suggested_actions[0].grounding["accessibility_name"] == "Wed, Oct 07, 2026"
    assert result.intent_dispatch is None


def test_ranked_result_selection_waits_for_requested_date():
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control()), prior_steps=[],
        result=proposal("Click the cheapest available result", "#other-result"),
    )
    assert result.suggested_actions[0].target_selector == "#departure"


def test_unrelated_route_link_cannot_preempt_date_on_requested_route_page():
    observed = page(control())
    observed.title = "A to B options"
    result = enforce_observed_date_before_result(
        task=TASK, page_context=observed, prior_steps=[],
        result=proposal("Click the link for B to C options", "#other-route"),
    )
    assert result.suggested_actions[0].target_selector == "#departure"


def test_route_link_on_unrelated_page_is_not_reordered():
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control()), prior_steps=[],
        result=proposal("Click the link for A to B options", "#right-route"),
    )
    assert result.suggested_actions[0].target_selector == "#right-route"


def test_wrong_route_link_is_blocked_after_requested_date_is_selected():
    observed = page(control(value="Tue, Oct 20, 2026"), prices=True)
    observed.title = "A to B options"
    observed.interactive_elements.append(InteractiveElement(
        type="a", role="link", text="B to C flight", selector="#wrong-route", visible=True,
        accessibility_name="B to C flight",
    ))
    result = enforce_observed_date_before_result(
        task=TASK, page_context=observed, prior_steps=[],
        result=proposal("Click the link for B to C flight", "#wrong-route"),
    )
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []


def test_selected_date_keeps_the_planned_action():
    original = proposal("Click the cheapest available result", "#option")
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control(value="Tue, Oct 20, 2026"), prices=True),
        prior_steps=[], result=original,
    )
    assert result.suggested_actions[0].target_selector == "#option"


def test_selected_date_without_priced_results_does_not_allow_cheapest_claim():
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control(value="Tue, Oct 20, 2026")),
        prior_steps=[], result=proposal("Click the cheapest available result", "#option"),
    )
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []


def test_ambiguous_date_controls_are_not_guessed():
    original = proposal("Click the cheapest available result", "#option")
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control("#date-one"), control("#date-two")),
        prior_steps=[], result=original,
    )
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []


def test_opening_date_control_does_not_count_as_selected_date():
    previous = PriorStep(
        action_type="click", target_selector="#departure", description="Open date", value=None,
        execution_result="CDP click dispatched via stable_selector grounding.\nExecution: success\nVerification: verified", page_analysis="", page_url="https://example.test/results",
    )
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control()), prior_steps=[previous],
        result=proposal("Click the cheapest available result", "#option"),
    )
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []


def test_open_calendar_uses_unique_full_date_option_before_result():
    previous = PriorStep(
        action_type="click", target_selector="#departure", description="Open date", value=None,
        execution_result="CDP click dispatched via stable_selector grounding.\nExecution: success\nVerification: verified", page_analysis="", page_url="https://example.test/results",
    )
    date_option = InteractiveElement(
        type="button", role="button", text="20", selector="#oct-20", visible=True,
        accessibility_name="Tue, Oct 20, 2026",
    )
    result = enforce_observed_date_before_result(
        task=TASK, page_context=page(control(), date_option), prior_steps=[previous],
        result=proposal("Click the cheapest available result", "#option"),
    )
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].target_selector == "#oct-20"
    assert result.suggested_actions[0].grounding["accessibility_name"] == "Tue, Oct 20, 2026"


def test_observed_route_opens_current_date_control_before_planner():
    observed = page(control())
    observed.title = "A to B options"
    result = observed_date_prerequisite_response(
        session_id="date", task=TASK, page_context=observed, prior_steps=[],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#departure"


def test_observed_calendar_uses_exact_full_date_after_opening():
    observed = page(control(), InteractiveElement(
        type="button", role="button", text="20", selector="#oct-20", visible=True,
        accessibility_name="Tue, Oct 20, 2026",
    ))
    observed.title = "A to B options"
    previous = PriorStep(
        action_type="click", target_selector="#departure", description="Open date", value=None,
        execution_result="CDP click dispatched via stable_selector grounding.\nExecution: success\nVerification: verified", page_analysis="", page_url="https://example.test/results",
    )
    result = observed_date_prerequisite_response(
        session_id="date", task=TASK, page_context=observed, prior_steps=[previous],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#oct-20"


def test_calendar_gridcell_requires_full_date_and_skips_disabled_option():
    observed = page(control(), InteractiveElement(
        type="div", role="gridcell", text="20", selector="#oct-20", visible=True,
        accessibility_name="Tuesday, 20 October 2026",
    ), InteractiveElement(
        type="div", role="gridcell", text="20", selector="#disabled-20", visible=True,
        accessibility_name="Tuesday, 20 October 2026", state={"aria_disabled": True},
    ))
    observed.title = "A to B options"
    previous = PriorStep(
        action_type="click", target_selector="#departure", description="Open date", value=None,
        execution_result="CDP click dispatched via stable_selector grounding.\nExecution: success\nVerification: verified",
        page_analysis="", page_url="https://example.test/results",
    )
    result = observed_date_prerequisite_response(
        session_id="date", task=TASK, page_context=observed, prior_steps=[previous],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#oct-20"


def test_observed_date_does_not_preempt_before_requested_route_is_current():
    assert observed_date_prerequisite_response(
        session_id="date", task=TASK, page_context=page(control()), prior_steps=[],
    ) is None


def test_route_results_date_button_with_embedded_date_is_opened_before_result_choice():
    observed = page(InteractiveElement(
        type="div", role="button", text="Date of journey06 Oct, 2026(Today)",
        selector="#journey-date", visible=True,
        accessibility_name="Edit journey date 06 Oct, 2026",
    ), prices=True)
    observed.url = "https://example.test/trips/hyderabad-to-bangalore?fromCityName=Hyderabad&toCityName=Bengaluru"
    observed.title = "Hyderabad to Bengaluru buses"
    task = "Find a bus from Hyderabad to Bengaluru on 20 October 2026 for one adult. Choose the cheapest."
    result = observed_date_prerequisite_response(
        session_id="date", task=task, page_context=observed, prior_steps=[],
    )
    assert result is not None
    assert result.suggested_actions[0].target_selector == "#journey-date"


def test_selected_date_is_committed_when_result_url_still_names_old_date():
    observed = page(
        InteractiveElement(type="div", role="button", text="Date of journey20 Oct, 2026",
                           selector="#journey-date", visible=True,
                           accessibility_name="Edit journey date 20 Oct, 2026"),
        InteractiveElement(type="button", role="button", text="Search buses",
                           selector="#search", visible=True, accessibility_name="Search buses"),
        InteractiveElement(type="div", role="radio", text="Price", selector="#price",
                           visible=True, accessibility_name="Price", state={"checked": False}),
    )
    observed.title = "Hyderabad to Bengaluru buses"
    observed.url = "https://example.test/hyderabad-to-bengaluru?onward=06-Oct-2026"
    task = "Find a bus from Hyderabad to Bengaluru on 20 October 2026. Choose the cheapest."
    response = observed_result_prerequisite_response(
        session_id="rank", task=task, page_context=observed, prior_steps=[],
    )
    assert response is not None
    assert response.suggested_actions[0].target_selector == "#search"
    assert "Commit the selected date" in response.suggested_actions[0].description
    assert observed_result_prerequisite_response(
        session_id="rank", task=task, page_context=observed,
        prior_steps=[PriorStep(action_type="click", target_selector="#search",
                              description="Commit the selected date with the observed search control",
                              value=None, execution_result="Execution: success", page_analysis="",
                              page_url=observed.url)],
    ).outcome_kind == "ask"


def test_price_radio_selected_only_after_date_and_url_agree():
    observed = page(
        InteractiveElement(type="div", role="button", text="Date of journey20 Oct, 2026",
                           selector="#journey-date", visible=True,
                           accessibility_name="Edit journey date 20 Oct, 2026"),
        InteractiveElement(type="div", role="radio", text="Price", selector="#price",
                           visible=True, accessibility_name="Price", state={"checked": False}),
    )
    observed.title = "Hyderabad to Bengaluru buses"
    observed.url = "https://example.test/hyderabad-to-bengaluru?onward=20-Oct-2026"
    task = "Find a bus from Hyderabad to Bengaluru on 20 October 2026. Choose the cheapest."
    response = observed_result_prerequisite_response(
        session_id="rank", task=task, page_context=observed, prior_steps=[],
    )
    assert response is not None
    assert response.suggested_actions[0].target_selector == "#price"
    observed.interactive_elements[1].state = {"checked": True}
    assert observed_result_prerequisite_response(
        session_id="rank", task=task, page_context=observed, prior_steps=[],
    ) is None
