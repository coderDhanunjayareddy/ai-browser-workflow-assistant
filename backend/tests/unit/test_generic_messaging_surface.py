from app.orchestrator.workflow_orchestrator import (
    _deterministic_observed_control_response,
    _deterministic_observed_report_response,
)
from app.schemas.request import InteractiveElement, PageContext, PriorStep


def _page(url: str, elements: list[InteractiveElement], visible_text: str = "") -> PageContext:
    return PageContext(
        url=url, title="Synthetic messaging surface", metadata={}, interactive_elements=elements,
        content_blocks=[], headings=[], selected_text="", visible_text=visible_text, images=[],
    )


def test_unknown_messaging_surface_opens_one_exact_observed_destination():
    page = _page("https://messaging-alpha.example/inbox", [
        InteractiveElement(
            type="div", role="row", selector="[data-result='casey']",
            text="Casey 10:42 Recent message", visible=True,
        ),
        InteractiveElement(
            type="div", role="row", selector="[data-result='casey-team']",
            text="Casey Team", visible=True,
        ),
    ])
    response = _deterministic_observed_control_response(
        session_id="generic-alpha", task='Open the exact chat named "Casey". Do not send anything.',
        page_context=page, prior_steps=[],
    )
    assert response is not None
    assert response.suggested_actions[0].target_selector == "[data-result='casey']"
    assert response.suggested_actions[0].grounding["accessibility_name"] == "Casey"
    assert "messaging destination" in response.suggested_actions[0].description


def test_structurally_different_surface_fills_observed_destination_search():
    page = _page("https://communications-beta.example/messages", [
        InteractiveElement(
            type="input", role="searchbox", selector="#people-filter",
            text="", accessibility_name="Search recipients", visible=True,
        ),
    ])
    response = _deterministic_observed_control_response(
        session_id="generic-beta", task='Find the exact contact named "Jordan" and open the conversation.',
        page_context=page, prior_steps=[],
    )
    assert response is not None
    action = response.suggested_actions[0]
    assert action.action_type == "fill"
    assert action.target_selector == "#people-filter"
    assert action.value == "Jordan"
    assert "communications-beta" not in action.description


def test_no_exact_result_stops_after_bounded_observation_instead_of_clicking_prefix():
    search = InteractiveElement(
        type="input", role="searchbox", selector="#recipient-search",
        text="", accessibility_name="Search contacts", state={"value": "Jordan"}, visible=True,
    )
    page = _page("https://communications-gamma.example/inbox", [
        search,
        InteractiveElement(type="div", role="row", selector="#jordan-team", text="Jordan Team", visible=True),
    ])
    prior_steps = [
        PriorStep(
            action_type="fill", description="Search exact destination", target_selector="#recipient-search",
            value="Jordan", execution_result="success",
        ),
        PriorStep(
            action_type="wait", description="Observe filtered results", target_selector="window",
            value="1000", execution_result="success",
        ),
    ]
    response = _deterministic_observed_control_response(
        session_id="generic-gamma", task='Open the exact recipient named "Jordan".',
        page_context=page, prior_steps=prior_steps,
    )
    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert "no exact visible match" in response.clarification_question.lower()


def test_verified_composer_allows_generic_content_insertion_but_not_submission():
    page = _page("https://messages-delta.example/thread/42", [
        InteractiveElement(
            type="textarea", role="textbox", selector="#composer",
            text="", accessibility_name="Type a message to Jordan", visible=True,
        ),
        InteractiveElement(
            type="button", role="button", selector="#attach",
            text="", accessibility_name="Attach", visible=True,
        ),
    ])
    response = _deterministic_observed_control_response(
        session_id="generic-delta",
        task='Open the exact chat named "Jordan" and attach the approved file "synthetic.txt". Do not send it.',
        page_context=page,
        prior_steps=[],
    )
    assert response is not None
    action = response.suggested_actions[0]
    assert action.content_insertion is not None
    assert action.consequential_submission is None
    assert action.target_selector == "#attach"


def test_verified_exact_open_report_is_host_independent():
    page = _page("https://messages-epsilon.example/thread/casey", [])
    prior_steps = [PriorStep(
        action_type="click", description="Open exact destination", target_selector="#casey",
        execution_result="success",
        browser_evidence={
            "adapter_exact_identity_verified": True,
            "adapter_exact_target_kind": "chat",
            "adapter_exact_expected_name": "Casey",
            "adapter_exact_observed_name": "Casey",
        },
    )]
    response = _deterministic_observed_report_response(
        session_id="generic-epsilon", task='Open the exact chat named "Casey". Do not send anything.',
        page_context=page, prior_steps=prior_steps,
    )
    assert response is not None
    assert response.sgv_verified is True
    assert "messaging destination" in response.report.answer
    assert "messages-epsilon" not in response.report.answer
