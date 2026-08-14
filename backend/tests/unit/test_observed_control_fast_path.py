from __future__ import annotations

from app.orchestrator.workflow_orchestrator import _deterministic_observed_control_response
from app.schemas.request import InteractiveElement, PageContext, PriorStep


def _page(url: str, elements: list[InteractiveElement]) -> PageContext:
    return PageContext(
        url=url,
        title="Fixture",
        metadata={},
        interactive_elements=elements,
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="",
        images=[],
    )


def test_login_controls_are_selected_in_fill_fill_submit_order() -> None:
    page = _page(
        "http://127.0.0.1:5051/login",
        [
            InteractiveElement(type="input", selector="#username", text="", visible=True, role="textbox"),
            InteractiveElement(type="input", selector="#password", text="", visible=True, role="textbox", input_type="password"),
            InteractiveElement(type="button", selector="#login-btn", text="Sign In", visible=True, role="button"),
        ],
    )
    task = 'Log in with username "tester" and password "secret123", then confirm the welcome message appears'

    username = _deterministic_observed_control_response(session_id="login", task=task, page_context=page, prior_steps=[])
    assert username is not None
    assert (username.suggested_actions[0].action_type, username.suggested_actions[0].target_selector, username.suggested_actions[0].value) == ("fill", "#username", "tester")

    password = _deterministic_observed_control_response(
        session_id="login",
        task=task,
        page_context=page,
        prior_steps=[PriorStep(action_type="fill", description="username", target_selector="#username", value="tester", execution_result="success")],
    )
    assert password is not None
    assert (password.suggested_actions[0].action_type, password.suggested_actions[0].target_selector, password.suggested_actions[0].value) == ("fill", "#password", "secret123")

    submit = _deterministic_observed_control_response(
        session_id="login",
        task=task,
        page_context=page,
        prior_steps=[
            PriorStep(action_type="fill", description="username", target_selector="#username", value="tester", execution_result="success"),
            PriorStep(action_type="fill", description="password", target_selector="#password", value="", execution_result="success"),
        ],
    )
    assert submit is not None
    assert (submit.suggested_actions[0].action_type, submit.suggested_actions[0].target_selector) == ("click", "#login-btn")


def test_pagination_and_modal_actions_use_observed_selectors() -> None:
    pagination = _deterministic_observed_control_response(
        session_id="pagination",
        task="Navigate to page 2 of the paged list and confirm page 2 items appear",
        page_context=_page(
            "http://127.0.0.1:5051/pagination",
            [InteractiveElement(type="a", selector="#p2", text="2", href="?page=2", visible=True, role="link")],
        ),
        prior_steps=[],
    )
    assert pagination is not None
    assert (pagination.suggested_actions[0].action_type, pagination.suggested_actions[0].target_selector) == ("click", "#p2")

    pagination_fallback = _deterministic_observed_control_response(
        session_id="pagination",
        task="Navigate to page 2 of the paged list and confirm page 2 items appear",
        page_context=_page(
            "http://127.0.0.1:5051/pagination",
            [
                InteractiveElement(type="a", selector="#p2", text="2", href="#", visible=True, role="link"),
                InteractiveElement(type="a", selector="#next", text="Next", href="#", visible=True, role="link"),
            ],
        ),
        prior_steps=[PriorStep(action_type="click", description="page 2", target_selector="#p2", execution_result="success")],
    )
    assert pagination_fallback is not None
    assert pagination_fallback.suggested_actions[0].target_selector == "#next"

    modal = _deterministic_observed_control_response(
        session_id="modal",
        task="Open the settings modal, then save the setting",
        page_context=_page(
            "http://127.0.0.1:5051/modal",
            [InteractiveElement(type="button", selector="#open", text="Open Modal", visible=True, role="button")],
        ),
        prior_steps=[],
    )
    assert modal is not None
    assert (modal.suggested_actions[0].action_type, modal.suggested_actions[0].target_selector) == ("click", "#open")
