from __future__ import annotations

from app.orchestrator.workflow_orchestrator import (
    _deterministic_observed_control_response,
    _deterministic_observed_report_response,
    _messaging_recipient_from_task,
)
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


def test_whatsapp_recipient_stops_before_trailing_safety_sentence() -> None:
    task = (
        "Open WhatsApp and open the exact direct chat named Teja Spc. "
        "Do not type a message, attach a file, or send anything."
    )

    assert _messaging_recipient_from_task(task) == "Teja Spc"


def test_exact_recipient_stops_before_next_positive_objective_sentence() -> None:
    task = (
        "Open the exact direct chat named Synthetic Recipient. "
        "Attach the approved synthetic document and verify its preview."
    )

    assert _messaging_recipient_from_task(task) == "Synthetic Recipient"


def test_whatsapp_login_page_pauses_without_selecting_login_controls() -> None:
    task = (
        "Open WhatsApp and open the exact direct chat named Teja Spc. "
        "Do not type a message, attach a file, or send anything."
    )
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="input",
                selector="#auto-logout-toggle",
                text="Stay logged in on this browser",
                visible=True,
            ),
        ],
    )
    page.visible_text = "Scan to log in Scan the QR code Stay logged in on this browser"

    response = _deterministic_observed_control_response(
        session_id="wa-auth",
        task=task,
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert "needs to be linked or signed in" in response.clarification_question


def test_whatsapp_open_only_task_reports_after_exact_chat_is_observed() -> None:
    task = (
        "Open WhatsApp and open the exact direct chat named Teja Spc. "
        "Do not type a message, attach a file, or send anything."
    )
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="div",
                selector='[data-testid="conversation-compose-box-input"]',
                text="",
                visible=True,
                role="textbox",
                accessibility_name="Type a message to Teja Spc",
            ),
            InteractiveElement(type="button", selector='button[aria-label="Attach"]', text="", visible=True),
        ],
    )

    report = _deterministic_observed_report_response(session_id="wa-open", task=task, page_context=page)
    control = _deterministic_observed_control_response(
        session_id="wa-open",
        task=task,
        page_context=page,
        prior_steps=[],
    )

    assert report is not None
    assert report.outcome_kind == "report"
    assert report.goal_convergence is True
    assert report.report is not None
    assert "Nothing was typed, attached, or sent" in report.report.answer
    assert control is None


def test_whatsapp_affirmative_attachment_task_does_not_finish_after_chat_open() -> None:
    task = "Open WhatsApp and open the exact chat named Teja Spc, then attach the approved file."
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="div",
                selector='[data-testid="conversation-compose-box-input"]',
                text="",
                visible=True,
                role="textbox",
                accessibility_name="Type a message to Teja Spc",
            ),
            InteractiveElement(
                type="button",
                selector='button[aria-label="Attach"]',
                text="",
                visible=True,
                accessibility_name="Attach",
            ),
        ],
    )

    assert _deterministic_observed_report_response(session_id="wa-attach", task=task, page_context=page) is None
    control = _deterministic_observed_control_response(
        session_id="wa-attach",
        task=task,
        page_context=page,
        prior_steps=[],
    )
    assert control is not None
    assert control.suggested_actions[0].description == (
        "Activate the observed content-insertion control for the broker-bound approved local_file content"
    )


def test_whatsapp_open_only_task_converges_from_trusted_exact_click_evidence() -> None:
    task = (
        "Open WhatsApp and open the exact direct chat named Teja Spc. "
        "Do not type a message, attach a file, or send anything."
    )
    page = _page("https://web.whatsapp.com/", [])
    click = PriorStep(
        action_type="click",
        description="Open the exact WhatsApp search result visibly named Teja Spc",
        target_selector='[role="row"]:has(span[title="Teja Spc"])',
        value=None,
        execution_result="success",
        browser_evidence={
            "adapter_exact_identity_verified": True,
            "adapter_exact_target_kind": "chat",
            "adapter_exact_expected_name": "Teja Spc",
            "adapter_exact_observed_name": "Teja Spc",
        },
    )

    report = _deterministic_observed_report_response(
        session_id="wa-evidence",
        task=task,
        page_context=page,
        prior_steps=[click],
    )

    assert report is not None
    assert report.outcome_kind == "report"
    assert report.goal_convergence is True


def test_generic_content_insertion_converges_from_exact_preview_evidence_without_send() -> None:
    task = (
        "Open the exact direct chat named Synthetic Recipient. "
        "Attach the explicitly approved synthetic document file named synthetic-day4.txt and verify its preview. "
        "Do not send anything."
    )
    page = _page("https://messaging.example.test/thread/123", [])
    selection = PriorStep(
        action_type="click",
        description="Activate the observed content-insertion control for the broker-bound approved document content",
        target_selector='button[aria-label="Document"]',
        value=None,
        execution_result="success",
        browser_evidence={
            "content_request_id": "content-test-1",
            "content_kind": "document",
            "destination_origin": "https://messaging.example.test",
            "destination_entity": "Synthetic Recipient",
            "upload_files_count": 1,
            "upload_accepted": True,
            "filename": "synthetic-day4.txt",
            "mime_type": "text/plain",
            "size_bytes": 64,
            "content_sha256": "a" * 64,
            "preview_identity_observed": True,
            "chooser_cancelled": False,
        },
    )

    report = _deterministic_observed_report_response(
        session_id="generic-preview",
        task=task,
        page_context=page,
        prior_steps=[selection],
    )

    assert report is not None
    assert report.outcome_kind == "report"
    assert report.goal_convergence is True
    assert report.report is not None
    assert report.report.answer == 'Attached and verified the preview for "synthetic-day4.txt". Nothing was sent.'


def test_generic_content_insertion_does_not_converge_for_wrong_origin_or_send_objective() -> None:
    page = _page("https://messaging.example.test/thread/123", [])
    evidence = {
        "content_request_id": "content-test-2",
        "destination_origin": "https://other.example.test",
        "destination_entity": "Synthetic Recipient",
        "upload_files_count": 1,
        "upload_accepted": True,
        "filename": "synthetic-day4.txt",
        "preview_identity_observed": True,
    }
    selection = PriorStep(
        action_type="click",
        description="Select exact approved content",
        target_selector="#document",
        value=None,
        execution_result="success",
        browser_evidence=evidence,
    )

    wrong_origin = _deterministic_observed_report_response(
        session_id="wrong-origin",
        task=(
            "Open the exact chat named Synthetic Recipient. Attach the file named synthetic-day4.txt. "
            "Do not send anything."
        ),
        page_context=page,
        prior_steps=[selection],
    )
    assert wrong_origin is None

    selection.browser_evidence["destination_origin"] = "https://messaging.example.test"
    send_requested = _deterministic_observed_report_response(
        session_id="send-requested",
        task=(
            "Open the exact chat named Synthetic Recipient. Attach the file named synthetic-day4.txt and send it."
        ),
        page_context=page,
        prior_steps=[selection],
    )
    assert send_requested is None


def test_generic_submission_is_built_only_from_exact_preview_destination_and_observed_control() -> None:
    task = (
        "Open the exact chat named Consenting Test Recipient. Attach synthetic-day5.txt and send it."
    )
    page = _page(
        "https://messaging.example.test/thread/123",
        [InteractiveElement(type="button", selector="#final-send", text="Send", visible=True, role="button")],
    )
    page.visible_text = "Consenting Test Recipient synthetic-day5.txt Send"
    preview = PriorStep(
        action_type="click",
        description="Select exact approved content",
        target_selector="#document",
        value=None,
        execution_result="success",
        browser_evidence={
            "destination_origin": "https://messaging.example.test",
            "destination_entity": "Consenting Test Recipient",
            "upload_files_count": 1,
            "upload_accepted": True,
            "filename": "synthetic-day5.txt",
            "preview_identity_observed": True,
        },
    )

    response = _deterministic_observed_control_response(
        session_id="generic-send",
        task=task,
        page_context=page,
        prior_steps=[preview],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert action.target_selector == "#final-send"
    assert action.safety_level == "danger"
    assert action.consequential_submission is not None
    assert action.consequential_submission["destination_entity"] == "Consenting Test Recipient"
    assert action.consequential_submission["content_identity"] == "synthetic-day5.txt"

    preview.browser_evidence["destination_entity"] = "Wrong Recipient"
    assert _deterministic_observed_control_response(
        session_id="generic-send",
        task=task,
        page_context=page,
        prior_steps=[preview],
    ) is None


def test_verified_generic_delivery_converges_without_redispatch() -> None:
    task = "Send synthetic-day5.txt to the exact chat named Consenting Test Recipient."
    page = _page("https://messaging.example.test/thread/123", [])
    delivery = PriorStep(
        action_type="click",
        description="Activate the observed final submission control for the verified content and destination",
        target_selector="#final-send",
        value=None,
        execution_result="success",
        browser_evidence={
            "submission_id": "submission-1",
            "submission_operation": "send",
            "submission_attempted": True,
            "delivery_verified": True,
            "delivered_content_identity": "synthetic-day5.txt",
            "delivered_destination_entity": "Consenting Test Recipient",
            "dispatch_uncertain": False,
        },
    )

    report = _deterministic_observed_report_response(
        session_id="generic-delivery",
        task=task,
        page_context=page,
        prior_steps=[delivery],
    )
    assert report is not None
    assert report.outcome_kind == "report"
    assert report.sgv_verified is True
    assert report.goal_convergence is True
    assert "exactly once" in report.report.answer


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


def test_table_edit_and_dynamic_ready_use_observed_controls() -> None:
    table = _deterministic_observed_control_response(
        session_id="table",
        task="Edit the first row in the customer table and confirm the row is updated",
        page_context=_page(
            "http://127.0.0.1:5051/crud",
            [
                InteractiveElement(type="button", selector='[data-testid="edit-1"]', text="Edit", visible=True, role="button"),
                InteractiveElement(type="button", selector='[data-testid="edit-2"]', text="Edit", visible=True, role="button"),
            ],
        ),
        prior_steps=[],
    )
    assert table is not None
    assert table.suggested_actions[0].target_selector == '[data-testid="edit-1"]'

    dynamic = _deterministic_observed_control_response(
        session_id="dynamic",
        task='Wait for the "Ready" button to appear and click it',
        page_context=_page(
            "http://127.0.0.1:5051/dynamic",
            [InteractiveElement(type="button", selector="#ready", text="Ready", visible=True, role="button")],
        ),
        prior_steps=[],
    )
    assert dynamic is not None
    assert dynamic.suggested_actions[0].target_selector == "#ready"


def test_upload_activates_observed_file_input_without_passing_a_local_path() -> None:
    response = _deterministic_observed_control_response(
        session_id="upload",
        task='Upload the test file "benchmark_test.txt" using the file input',
        page_context=_page(
            "http://127.0.0.1:5051/upload",
            [InteractiveElement(type="input", input_type="file", selector="#file", text="", visible=True)],
        ),
        prior_steps=[],
    )

    assert response is not None
    assert (response.suggested_actions[0].action_type, response.suggested_actions[0].target_selector) == ("click", "#file")
    assert response.suggested_actions[0].value == ""


def test_attachment_trigger_is_grounded_generically_on_an_unregistered_provider() -> None:
    response = _deterministic_observed_control_response(
        session_id="generic-attachment",
        task='Attach the approved document "synthetic-day4.pdf" without sending it.',
        page_context=_page(
            "https://messaging.example.test/thread/123",
            [InteractiveElement(type="button", selector="#paperclip", text="", visible=True, accessibility_name="Attach")],
        ),
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert (action.action_type, action.target_selector) == ("click", "#paperclip")
    assert "content-insertion control" in action.description
    assert "WhatsApp" not in action.description


def test_content_insertion_prefers_composer_trigger_over_unrelated_global_media_navigation() -> None:
    response = _deterministic_observed_control_response(
        session_id="generic-composer-boundary",
        task='Attach the approved document "synthetic-day4.txt" without sending it.',
        page_context=_page(
            "https://messaging.example.test/thread/123",
            [
                InteractiveElement(
                    type="button",
                    selector='button[aria-label="Media"]',
                    text="",
                    visible=True,
                    role="button",
                    aria_label="Media",
                ),
                InteractiveElement(
                    type="div",
                    selector='div[aria-label="Write a message"]',
                    text="",
                    visible=True,
                    role="textbox",
                    aria_label="Write a message",
                ),
                InteractiveElement(
                    type="button",
                    selector='button[aria-label="Attach"]',
                    text="",
                    visible=True,
                    role="button",
                    aria_label="Attach",
                ),
            ],
        ),
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert (action.action_type, action.target_selector) == ("click", 'button[aria-label="Attach"]')
    assert action.content_insertion is not None
    assert action.content_insertion["stage"] == "open_insertion_menu"
    assert action.content_insertion["opens_native_chooser"] is False


def test_site_search_fills_observed_field_then_uses_canonical_results_url() -> None:
    task = 'Search for "fastapi" repositories on GitHub and confirm repositories appear in results'
    page = _page(
        "https://github.com/search?type=repositories",
        [
            InteractiveElement(
                type="input",
                selector='input[aria-label="Search GitHub"]',
                text="",
                visible=True,
                role="textbox",
                aria_label="Search GitHub",
            )
        ],
    )

    fill = _deterministic_observed_control_response(session_id="search", task=task, page_context=page, prior_steps=[])
    assert fill is not None
    assert (fill.suggested_actions[0].action_type, fill.suggested_actions[0].value) == ("fill", "fastapi")

    submit = _deterministic_observed_control_response(
        session_id="search",
        task=task,
        page_context=page,
        prior_steps=[
            PriorStep(
                action_type="fill",
                description="site search",
                target_selector='input[aria-label="Search GitHub"]',
                value="fastapi",
                execution_result="success",
            )
        ],
    )
    assert submit is not None
    assert (submit.suggested_actions[0].action_type, submit.suggested_actions[0].target_selector, submit.suggested_actions[0].value) == (
        "navigate",
        "window",
        "https://github.com/search?type=repositories&q=fastapi",
    )


def test_whatsapp_search_opens_visible_exact_chat_without_empty_enter() -> None:
    task = 'Open WhatsApp. Search for the exact chat named "Teja Spc" (or click it if already visible). Open only that exact chat. Attach the approved local file "C:\\Downloads\\synthetic.png".'
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="div",
                selector='div[aria-label="Search input textbox"]',
                text="",
                visible=True,
                role="textbox",
                aria_label="Search input textbox",
            ),
            InteractiveElement(type="span", selector='span[title="Teja Spc"]', text="Teja Spc", visible=True),
        ],
    )

    response = _deterministic_observed_control_response(session_id="wa", task=task, page_context=page, prior_steps=[])

    assert response is not None
    assert (response.suggested_actions[0].action_type, response.suggested_actions[0].target_selector) == (
        "click",
        '[role="row"]:has(span[title="Teja Spc"])',
    )


def test_whatsapp_unquoted_recipient_fills_contact_search_instead_of_enter() -> None:
    task = "Open WhatsApp and search for the exact chat named Teja Spc, then attach the approved file."
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="div",
                selector='div[aria-label="Search input textbox"]',
                text="",
                visible=True,
                role="textbox",
                aria_label="Search input textbox",
            )
        ],
    )

    response = _deterministic_observed_control_response(session_id="wa", task=task, page_context=page, prior_steps=[])

    assert response is not None
    assert (response.suggested_actions[0].action_type, response.suggested_actions[0].value) == ("fill", "Teja Spc")


def test_whatsapp_filtered_exact_visible_result_is_opened_when_virtualized_row_is_not_extracted() -> None:
    task = 'Open WhatsApp and open the exact chat named "Teja Spc". Attach the approved file "synthetic.png".'
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="input",
                selector="#chat-search",
                text="",
                visible=True,
                role="textbox",
                accessibility_name="Search",
            )
        ],
    )
    page.visible_text = "Chats\nTeja Spc\nHaha\nGroups in common"

    response = _deterministic_observed_control_response(
        session_id="wa",
        task=task,
        page_context=page,
        prior_steps=[
            PriorStep(
                action_type="fill",
                description="contact search",
                target_selector="#chat-search",
                value="Teja Spc",
                execution_result=(
                    "Filled field\n\n"
                    "Recommendation: Treat the action as having produced the intended browser effect."
                ),
            )
        ],
    )

    assert response is not None
    assert (response.suggested_actions[0].action_type, response.suggested_actions[0].target_selector) == (
        "click",
        '[role="row"]:has(span[title="Teja Spc"])',
    )


def test_whatsapp_current_search_value_grounds_exact_virtualized_contact_click() -> None:
    task = 'Open WhatsApp and open the exact chat named "Teja Spc". Attach the approved file "synthetic.png".'
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="input",
                selector="#_r_a_",
                text="",
                visible=True,
                role="textbox",
                accessibility_name="",
                state={"value": "Teja Spc"},
            )
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="wa",
        task=task,
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert (response.suggested_actions[0].action_type, response.suggested_actions[0].target_selector) == (
        "click",
        '[role="row"]:has(span[title="Teja Spc"])',
    )


def test_whatsapp_open_chat_advances_to_observed_attachment_control() -> None:
    task = "Open WhatsApp, search for the exact chat named Teja Spc, open that chat, attach the approved file, and send it."
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="div",
                selector='div[aria-label="Search input textbox"]',
                text="",
                visible=True,
                role="textbox",
                aria_label="Search input textbox",
            ),
            InteractiveElement(
                type="div",
                selector='div[aria-label="Type a message"]',
                text="",
                visible=True,
                role="textbox",
                aria_label="Type a message",
            ),
            InteractiveElement(type="button", selector='button[aria-label="Attach"]', text="", visible=True, role="button", aria_label="Attach"),
        ],
    )

    response = _deterministic_observed_control_response(session_id="wa", task=task, page_context=page, prior_steps=[])

    assert response is not None
    assert (response.suggested_actions[0].action_type, response.suggested_actions[0].target_selector) == (
        "click",
        'button[aria-label="Attach"]',
    )


def test_wizard_controls_follow_visible_step_and_explicit_values() -> None:
    task = 'Complete the onboarding wizard: enter full name "Test User" in step 1, then enter role "Engineer" in step 2, then click Finish'
    step_one = _page(
        "http://127.0.0.1:5051/multistep",
        [
            InteractiveElement(type="input", selector="#fullname", text="", visible=True, role="textbox", accessibility_name="Full name"),
            InteractiveElement(type="button", selector="#next1", text="Next", visible=True, role="button"),
        ],
    )
    fill_name = _deterministic_observed_control_response(session_id="wizard", task=task, page_context=step_one, prior_steps=[])
    assert fill_name is not None
    assert (fill_name.suggested_actions[0].action_type, fill_name.suggested_actions[0].target_selector, fill_name.suggested_actions[0].value) == ("fill", "#fullname", "Test User")

    click_next = _deterministic_observed_control_response(
        session_id="wizard",
        task=task,
        page_context=step_one,
        prior_steps=[PriorStep(action_type="fill", description="full name", target_selector="#fullname", value="Test User", execution_result="success")],
    )
    assert click_next is not None
    assert (click_next.suggested_actions[0].action_type, click_next.suggested_actions[0].target_selector) == ("click", "#next1")

    step_two = _page(
        "http://127.0.0.1:5051/multistep",
        [
            InteractiveElement(type="input", selector="#role", text="", visible=True, role="textbox", accessibility_name="Role"),
            InteractiveElement(type="button", selector="#finish", text="Finish", visible=True, role="button"),
        ],
    )
    fill_role = _deterministic_observed_control_response(session_id="wizard", task=task, page_context=step_two, prior_steps=[])
    assert fill_role is not None
    assert (fill_role.suggested_actions[0].action_type, fill_role.suggested_actions[0].target_selector, fill_role.suggested_actions[0].value) == ("fill", "#role", "Engineer")


def test_load_more_and_quoted_accordion_controls_are_grounded() -> None:
    load_more = _deterministic_observed_control_response(
        session_id="scroll",
        task="Scroll the feed to load more posts until at least 6 posts are visible",
        page_context=_page(
            "http://127.0.0.1:5051/scroll",
            [InteractiveElement(type="button", selector="#more", text="Load more", visible=True, role="button")],
        ),
        prior_steps=[],
    )
    assert load_more is not None
    assert (load_more.suggested_actions[0].action_type, load_more.suggested_actions[0].target_selector) == ("click", "#more")

    accordion = _deterministic_observed_control_response(
        session_id="accordion",
        task='Expand the second FAQ question ("How much?") and confirm its answer is visible',
        page_context=_page(
            "http://127.0.0.1:5051/accordion",
            [
                InteractiveElement(
                    type="summary",
                    selector="#q2 > summary",
                    text="How much?",
                    visible=True,
                    accessibility_name="How much?",
                )
            ],
        ),
        prior_steps=[],
    )
    assert accordion is not None
    assert (accordion.suggested_actions[0].action_type, accordion.suggested_actions[0].target_selector) == ("click", "#q2 > summary")


def test_registration_with_missing_credentials_asks_instead_of_fabricating_values() -> None:
    response = _deterministic_observed_control_response(
        session_id="register",
        task=(
            "Complete the registration form: enter name into email/password fields, "
            'select country "India", accept terms, then submit'
        ),
        page_context=_page(
            "http://127.0.0.1:5051/register",
            [
                InteractiveElement(type="input", input_type="email", selector="#email", text="", visible=True, accessibility_name="Email"),
                InteractiveElement(type="input", input_type="password", selector="#pw", text="", visible=True, accessibility_name="Password"),
                InteractiveElement(type="button", selector="#reg-btn", text="Register", visible=True, role="button"),
            ],
        ),
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert response.clarification_question is not None
    assert "email address and password" in response.clarification_question


def test_public_selenium_test_form_uses_non_sensitive_fake_data_then_submits() -> None:
    task = (
        "Fill the form with clearly fake test data, check validation errors, and submit only if it is "
        "a genuine test or sandbox form."
    )
    page = _page(
        "https://www.selenium.dev/selenium/web/web-form.html",
        [
            InteractiveElement(type="input", input_type="text", selector="#my-text-id", text="", visible=True),
            InteractiveElement(type="textarea", selector="textarea", text="", visible=True),
            InteractiveElement(type="select", selector="select", text="One Two Three", visible=True, role="combobox"),
            InteractiveElement(type="button", selector="button", text="Submit", visible=True, role="button"),
        ],
    )

    first = _deterministic_observed_control_response(session_id="form", task=task, page_context=page, prior_steps=[])
    assert first is not None
    assert (first.suggested_actions[0].action_type, first.suggested_actions[0].target_selector) == ("fill", "#my-text-id")

    steps = [PriorStep(action_type="fill", description="fake name", target_selector="#my-text-id", value="", execution_result="success")]
    second = _deterministic_observed_control_response(session_id="form", task=task, page_context=page, prior_steps=steps)
    assert second is not None
    assert (second.suggested_actions[0].action_type, second.suggested_actions[0].target_selector) == ("fill", "textarea")

    steps.append(PriorStep(action_type="fill", description="fake note", target_selector="textarea", value="", execution_result="success"))
    third = _deterministic_observed_control_response(session_id="form", task=task, page_context=page, prior_steps=steps)
    assert third is not None
    assert (third.suggested_actions[0].action_type, third.suggested_actions[0].target_selector, third.suggested_actions[0].value) == ("select_option", "select", "One")

    steps.append(PriorStep(action_type="select_option", description="choice", target_selector="select", value="One", execution_result="success"))
    fourth = _deterministic_observed_control_response(session_id="form", task=task, page_context=page, prior_steps=steps)
    assert fourth is not None
    assert (fourth.suggested_actions[0].action_type, fourth.suggested_actions[0].target_selector) == ("click", "button")


def test_public_selenium_test_form_reports_only_from_confirmation_page() -> None:
    task = "Fill with test data, check validation errors, submit, and report whether submission succeeded."
    page = _page("https://www.selenium.dev/selenium/web/submitted-form.html", [])
    page = page.model_copy(update={"visible_text": "Form submitted Received!"})

    report = _deterministic_observed_report_response(session_id="form", task=task, page_context=page)

    assert report is not None
    assert report.outcome_kind == "report"
    assert report.report is not None
    assert "Submission succeeded" in report.report.answer


def test_invoice_total_is_reported_from_visible_evidence() -> None:
    page = _page("http://127.0.0.1:5051/invoice", [])
    page = page.model_copy(update={
        "visible_text": "Invoice INV-2026-0711 Billing Summary Subtotal INR 12,400.00 Tax INR 2,232.00 Total Due INR 14,632.00",
    })

    report = _deterministic_observed_report_response(
        session_id="invoice",
        task="Tell me the invoice total.",
        page_context=page,
    )

    assert report is not None
    assert report.outcome_kind == "report"
    assert report.report is not None
    assert report.report.answer == "INR 14,632.00"
