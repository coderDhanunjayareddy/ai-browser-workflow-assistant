from __future__ import annotations

from app.orchestrator.workflow_orchestrator import (
    _deterministic_human_intervention_response,
    _destination_ordinal_from_task,
    _content_insertion_destination_entity,
    _content_insertion_effect,
    _composer_destination_candidates,
    _exact_identity_key,
    _deterministic_observed_control_response,
    _deterministic_observed_report_response,
    _find_observed_control,
    _messaging_recipient_from_task,
)
from app.schemas.request import InteractiveElement, PageContext, PriorStep


def _page(url: str, elements: list[InteractiveElement]) -> PageContext:
    return PageContext(
        tab_id=7,
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


def test_recipient_identity_is_separate_from_explicit_ordinal_disambiguation() -> None:
    task = "Open WhatsApp and search for Ramu (Nanna) the first chat, then attach synthetic-day5.txt."

    assert _messaging_recipient_from_task(task) == "Ramu (Nanna)"
    assert _destination_ordinal_from_task(task) == 1


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
            InteractiveElement(
                type="button", selector="#phone-link", text="Link with phone number",
                visible=True, role="button",
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
    assert response.clarification_question is None
    intervention = response.human_intervention
    assert intervention is not None
    assert intervention["kind"] == "authentication"
    assert intervention["secret_handling"] == "direct_browser_only"
    assert intervention["resume_condition"]["tab_id"] == 7
    assert intervention["resume_condition"]["observed_origin"] == "https://web.whatsapp.com"
    assert "password" not in intervention["requested_action"].casefold()


def test_generic_authentication_gate_is_not_bound_to_a_named_provider() -> None:
    page = _page(
        "https://portal.example.test/session",
        [InteractiveElement(
            type="input", input_type="password", selector="#credential", text="", visible=True,
            accessibility_name="Account credential",
        )],
    )
    page.title = "Member access"
    page.visible_text = "Use your account to continue"

    response = _deterministic_human_intervention_response(
        session_id="generic-auth", task="Continue the requested portal workflow", page_context=page,
    )

    assert response is not None
    assert response.human_intervention["kind"] == "authentication"
    assert response.human_intervention["resume_condition"]["observed_origin"] == "https://portal.example.test"
    assert not any(name in str(response.human_intervention).casefold() for name in ("whatsapp", "gmail", "linkedin"))


def test_missing_named_control_in_cross_origin_frame_returns_meaningful_safe_boundary() -> None:
    page = _page("https://outer.example.test/workspace", [])
    page.metadata = {"same_origin_child_frame_count": "0", "cross_origin_child_frame_count": "1"}
    page.visible_text = "Outer workspace"

    response = _deterministic_observed_control_response(
        session_id="origin-boundary",
        task=(
            "Click the exact control named Transfer Data inside the embedded external account frame once. "
            "Do not click any substitute."
        ),
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert "cross-origin embedded frame" in response.analysis
    assert "no substitute target" in response.analysis.lower()
    assert "verify and resume" in response.clarification_question.lower()


def test_required_auth_heading_and_human_control_form_a_structural_gate() -> None:
    page = _page(
        "https://workspace.example.test/gate",
        [InteractiveElement(
            type="button", role="button", selector="#human-auth", text="Complete sign in", visible=True,
            accessibility_name="Complete sign in",
        )],
    )
    page.title = "Workspace authentication"
    page.headings = ["Sign in required"]
    page.visible_text = "Human authentication is required. Complete sign in."

    response = _deterministic_human_intervention_response(
        session_id="structural-auth", task="Continue to the workspace", page_context=page,
    )

    assert response is not None
    assert response.human_intervention["kind"] == "authentication"


def test_login_words_in_page_prose_do_not_create_a_false_intervention() -> None:
    page = _page(
        "https://docs.example.test/article",
        [InteractiveElement(type="button", selector="#next", text="Next", visible=True)],
    )
    page.title = "Migration guide"
    page.visible_text = "This article explains how users log in to an older system."

    assert _deterministic_human_intervention_response(
        session_id="generic-read", task="Summarize this article", page_context=page,
    ) is None


def test_optional_login_link_on_public_content_is_not_a_blocking_gate() -> None:
    page = _page(
        "https://knowledge.example.test/article",
        [
            InteractiveElement(
                type="a", role="link", selector="#login", text="Log in", visible=True,
                accessibility_name="Log in",
            ),
            InteractiveElement(
                type="button", role="button", selector="#contents", text="Contents", visible=True,
            ),
        ],
    )
    page.title = "Public automation article"
    page.headings = ["Browser automation"]
    page.visible_text = "Browser automation Contents Log in"

    assert _deterministic_human_intervention_response(
        session_id="public-optional-login", task="Verify the visible article title", page_context=page,
    ) is None


def test_passwordless_login_form_is_still_a_blocking_gate() -> None:
    page = _page(
        "https://accounts.example.test/access",
        [
            InteractiveElement(
                type="input", role="textbox", selector="#email", text="", visible=True,
                accessibility_name="Email address",
            ),
            InteractiveElement(
                type="button", role="button", selector="#continue", text="Continue with email", visible=True,
            ),
        ],
    )
    page.title = "Member access"

    response = _deterministic_human_intervention_response(
        session_id="passwordless-login", task="Continue to the workspace", page_context=page,
    )

    assert response is not None
    assert response.human_intervention["kind"] == "authentication"


def test_login_prose_does_not_abort_a_grounded_destination_action() -> None:
    page = _page(
        "https://messaging.example.test/inbox",
        [
            InteractiveElement(
                type="input", selector="#search", text="", visible=True, role="searchbox",
                accessibility_name="Search contacts",
            ),
            InteractiveElement(
                type="div", selector="#recipient", text="Example Recipient", visible=True, role="listitem",
                accessibility_name="Example Recipient",
            ),
        ],
    )
    page.visible_text = "Chats Contacts This help article explains how users log in."

    response = _deterministic_observed_control_response(
        session_id="generic-prose-action",
        task="Open the exact direct chat named Example Recipient. Do not send anything.",
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.human_intervention is None
    assert response.suggested_actions[0].target_selector == "#recipient"


def test_mfa_and_captcha_are_classified_before_general_authentication() -> None:
    mfa_page = _page(
        "https://portal.example.test/verify",
        [InteractiveElement(
            type="input", selector="#code", text="", visible=True,
            accessibility_name="Verification code",
        )],
    )
    mfa_page.title = "Sign in verification"
    mfa_response = _deterministic_human_intervention_response(
        session_id="generic-mfa", task="Continue the portal workflow", page_context=mfa_page,
    )
    assert mfa_response.human_intervention["kind"] == "mfa"

    captcha_page = _page(
        "https://portal.example.test/challenge",
        [InteractiveElement(
            type="iframe", selector="#challenge", text="", visible=True,
            accessibility_name="reCAPTCHA",
        )],
    )
    captcha_page.visible_text = "Verify you are human"
    captcha_response = _deterministic_human_intervention_response(
        session_id="generic-captcha", task="Continue the portal workflow", page_context=captcha_page,
    )
    assert captcha_response.human_intervention["kind"] == "captcha"


def test_captcha_words_in_public_prose_do_not_create_a_false_gate() -> None:
    page = _page(
        "https://knowledge.example.test/security-article",
        [InteractiveElement(type="a", role="link", selector="#next", text="Next article", visible=True)],
    )
    page.title = "CAPTCHA - encyclopedia article"
    page.headings = ["CAPTCHA", "Verify you are human interfaces"]
    page.visible_text = "This article explains CAPTCHA, reCAPTCHA, and how users verify they are human."

    assert _deterministic_human_intervention_response(
        session_id="captcha-prose", task="Summarize the public article", page_context=page,
    ) is None


def test_exact_visible_marker_report_is_generic_and_evidence_backed() -> None:
    page = _page("https://workspace.example.test/ready", [])
    page.title = "Workspace ready"
    page.visible_text = "Automation may resume. fixture_state=authenticated"

    response = _deterministic_observed_report_response(
        session_id="generic-visible-marker",
        task=(
            'After authentication, report the exact visible marker '
            '"fixture_state=authenticated". Do not click or submit anything.'
        ),
        page_context=page,
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.backend_authoritative_report is True
    assert response.suggested_actions == []
    assert "fixture_state=authenticated" in response.report.answer


def test_named_native_selection_and_date_follow_task_order() -> None:
    task = (
        "Select 'High' in the exact enabled control named Priority. "
        "Choose date '2026-09-30' in the exact enabled control named Due date."
    )
    page = _page(
        "https://forms.example.test/preview",
        [
            InteractiveElement(
                type="select", role="combobox", selector="#priority", text="", visible=True,
                accessibility_name="Priority",
            ),
            InteractiveElement(
                type="input", input_type="date", selector="#due", text="", visible=True,
                accessibility_name="Due date",
            ),
        ],
    )

    first = _deterministic_observed_control_response(
        session_id="generic-selections", task=task, page_context=page, prior_steps=[],
    )
    assert first is not None
    assert first.suggested_actions[0].action_type == "select_option"
    assert first.suggested_actions[0].target_selector == "#priority"
    assert first.suggested_actions[0].value == "High"

    second = _deterministic_observed_control_response(
        session_id="generic-selections",
        task=task,
        page_context=page,
        prior_steps=[PriorStep(
            action_type="select_option", description="priority", target_selector="#priority",
            value="High", execution_result="CDP select_option dispatched via stable_selector grounding.",
        )],
    )
    assert second is not None
    assert second.suggested_actions[0].action_type == "choose_date"
    assert second.suggested_actions[0].target_selector == "#due"
    assert second.suggested_actions[0].value == "2026-09-30"


def test_natural_compound_form_assignments_do_not_depend_on_observed_control_order() -> None:
    task = (
        "Fill the exact field named Project title with Cross-domain audit. "
        "Select High in the exact control named Priority. "
        "Choose 2026-09-30 in the exact control named Due date. "
        "Activate the exact enabled control named Preview exactly once."
    )
    page = _page(
        "https://forms.example.test/preview",
        [
            InteractiveElement(type="button", role="button", selector="#random-preview", text="Preview", visible=True, accessibility_name="Preview"),
            InteractiveElement(type="input", input_type="date", selector="#random-due", text="", visible=True, accessibility_name="Due date"),
            InteractiveElement(type="select", role="combobox", selector="#random-priority", text="", visible=True, accessibility_name="Priority"),
            InteractiveElement(type="input", role="textbox", selector="#random-title", text="", visible=True, accessibility_name="Project title"),
        ],
    )
    prior: list[PriorStep] = []
    expected = [
        ("fill", "#random-title", "Cross-domain audit"),
        ("select_option", "#random-priority", "High"),
        ("choose_date", "#random-due", "2026-09-30"),
        ("click", "#random-preview", "Preview"),
    ]
    for index, (action_type, selector, value) in enumerate(expected):
        response = _deterministic_observed_control_response(
            session_id="random-natural-form", task=task, page_context=page, prior_steps=prior,
        )
        assert response is not None
        assert response.outcome_kind == "act"
        action = response.suggested_actions[0]
        assert (action.action_type, action.target_selector, action.value) == (action_type, selector, value)
        prior.append(PriorStep(
            action_type=action_type,
            description=f"step {index}",
            target_selector=selector,
            value=value,
            execution_result="success",
        ))


def test_completed_assignments_are_not_reinterpreted_as_clicks_in_a_compound_form_task() -> None:
    task = (
        "Select 'High' in the exact enabled control named Priority. "
        "Choose date '2026-09-30' in the exact enabled control named Due date. "
        "Activate the exact enabled Preview control once."
    )
    page = _page(
        "https://forms.example.test/preview",
        [
            InteractiveElement(type="select", role="combobox", selector="#priority", text="", visible=True, accessibility_name="Priority"),
            InteractiveElement(type="input", input_type="date", selector="#due", text="", visible=True, accessibility_name="Due date"),
            InteractiveElement(type="button", role="button", selector="#preview", text="Preview", visible=True, accessibility_name="Preview"),
        ],
    )
    prior = [
        PriorStep(
            action_type="select_option", description="priority", target_selector="#priority",
            value="High", execution_result="CDP select_option dispatched via stable_selector grounding.",
        ),
        PriorStep(
            action_type="choose_date", description="due date", target_selector="#due",
            value="2026-09-30", execution_result="CDP choose_date dispatched via stable_selector grounding.",
        ),
    ]

    response = _deterministic_observed_control_response(
        session_id="compound-form", task=task, page_context=page, prior_steps=prior,
    )

    assert response is not None
    assert response.suggested_actions[0].action_type == "click"
    assert response.suggested_actions[0].target_selector == "#preview"
    assert response.suggested_actions[0].value == "Preview"


def test_ambiguous_named_selection_fails_closed() -> None:
    page = _page(
        "https://forms.example.test/preview",
        [
            InteractiveElement(type="select", role="combobox", selector="#a", text="", visible=True, accessibility_name="Priority"),
            InteractiveElement(type="select", role="combobox", selector="#b", text="", visible=True, accessibility_name="Priority"),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="ambiguous-selection",
        task="Select 'High' in the exact enabled control named Priority.",
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []


def test_verified_cdp_fill_is_preserved_when_later_selection_needs_recovery() -> None:
    page = _page(
        "https://forms.example.test/preview",
        [
            InteractiveElement(type="input", role="textbox", selector="#title", text="", visible=True, accessibility_name="Project title"),
            InteractiveElement(type="select", role="combobox", selector="#priority", text="", visible=True, accessibility_name="Priority"),
        ],
    )
    task = (
        "In the visible Project title field enter 'Cross-domain audit'. "
        "Select 'High' in the exact enabled control named Priority."
    )
    prior = [
        PriorStep(
            action_type="fill", description="title", target_selector="#title", value="Cross-domain audit",
            execution_result="CDP fill dispatched via stable_selector grounding.",
        ),
        PriorStep(
            action_type="select_option", description="priority", target_selector="#priority", value="High",
            execution_result="CDP select_option dispatched via stable_selector grounding. Canonical effect verification reported no_effect.",
        ),
    ]

    response = _deterministic_observed_control_response(
        session_id="preserve-fill", task=task, page_context=page, prior_steps=prior,
    )

    assert response is not None
    assert response.suggested_actions[0].action_type == "select_option"
    assert response.suggested_actions[0].target_selector == "#priority"


def test_visible_marker_report_does_not_claim_an_unobserved_marker() -> None:
    page = _page("https://workspace.example.test/ready", [])
    page.visible_text = "Workspace is still loading"

    response = _deterministic_observed_report_response(
        session_id="generic-visible-marker-missing",
        task='Report the exact visible marker "fixture_state=authenticated".',
        page_context=page,
    )

    assert response is None


def test_exact_visible_text_marker_phrase_reports_without_planner() -> None:
    page = _page("https://unfamiliar.example.test/", [])
    page.visible_text = "Example Domain\nThis is a neutral public page."

    response = _deterministic_observed_report_response(
        session_id="exact-visible-text-marker",
        task="Open the page and verify the exact visible text marker 'Example Domain'.",
        page_context=page,
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.report.answer == 'Verified the visible marker "Example Domain".'


def test_verified_generic_mutation_reports_only_after_requested_state_is_observed() -> None:
    page = _page("http://127.0.0.1:8765/semantic-grounding-fixture.html", [])
    page.visible_text = "fixture_state=continued_exactly_once"
    task = (
        "Open the unfamiliar workspace and activate the exact enabled control named Continue once. "
        "Verify the state becomes continued exactly once."
    )
    verified_click = PriorStep(
        action_type="click",
        description="Activate the grounded exact control: Continue",
        target_selector="#exact-control",
        value="Continue",
        execution_result="Clicked target\n\nExecution: success\nVerification: verified",
        page_url=page.url,
        page_title=page.title,
    )

    response = _deterministic_observed_report_response(
        session_id="generic-state-postcondition",
        task=task,
        page_context=page,
        prior_steps=[verified_click],
    )
    without_mutation = _deterministic_observed_report_response(
        session_id="generic-state-no-mutation",
        task=task,
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.suggested_actions == []
    assert without_mutation is None


def test_generic_postcondition_accepts_canonical_persisted_success_result() -> None:
    page = _page("https://unfamiliar.example.test/workspace", [])
    page.visible_text = "fixture_state=continued_exactly_once"
    task = "Activate Continue once. Verify the state becomes continued exactly once."
    persisted_click = PriorStep(
        action_type="click",
        description="Activate the grounded exact control: Continue",
        target_selector="#exact-control",
        value="Continue",
        execution_result="success",
        page_url=page.url,
        page_title=page.title,
    )

    response = _deterministic_observed_report_response(
        session_id="generic-canonical-success-postcondition",
        task=task,
        page_context=page,
        prior_steps=[persisted_click],
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.suggested_actions == []


def test_opened_destination_identity_terminates_after_verified_exact_click() -> None:
    page = _page("https://code.example.test/acme/runner", [])
    page.title = "acme/runner"
    page.visible_text = "acme runner Public project"
    task = (
        "Open the public project search. Activate the exact visible link named acme/runner exactly once. "
        "Verify that the opened project identity is acme/runner. Do not sign in or change external data."
    )
    exact_click = PriorStep(
        action_type="click",
        description="Activate the grounded exact control: acme/runner",
        target_selector='a[href="/acme/runner"]',
        value="acme/runner",
        execution_result="success",
        page_url=page.url,
        page_title=page.title,
    )

    response = _deterministic_observed_report_response(
        session_id="generic-opened-identity",
        task=task,
        page_context=page,
        prior_steps=[exact_click],
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.suggested_actions == []
    assert "acme/runner" in response.report.answer


def test_opened_destination_identity_requires_verified_mutation() -> None:
    page = _page("https://code.example.test/acme/runner", [])
    page.visible_text = "acme runner Public project"

    response = _deterministic_observed_report_response(
        session_id="generic-opened-identity-no-mutation",
        task="Verify that the opened project identity is acme/runner.",
        page_context=page,
        prior_steps=[],
    )

    assert response is None


def test_generic_postcondition_accepts_identifier_named_state_clause() -> None:
    page = _page("https://unfamiliar.example.test/workspace", [])
    page.visible_text = "fixture_state=continued_exactly_once"
    persisted_click = PriorStep(
        action_type="click",
        description="Activate the grounded exact control: Continue",
        target_selector="#exact-control",
        value="Continue",
        execution_result="success",
        page_url=page.url,
        page_title=page.title,
    )

    response = _deterministic_observed_report_response(
        session_id="generic-identifier-state-postcondition",
        task="Activate Continue. Verify fixture_state becomes continued_exactly_once.",
        page_context=page,
        prior_steps=[persisted_click],
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.report.answer == 'Verified that the requested state became "continued_exactly_once".'


def test_generic_postcondition_accepts_compact_state_assignment_without_planner() -> None:
    page = _page("https://unfamiliar.example.test/workspace", [])
    page.visible_text = "fixture_state=dynamic_dialog_completed_exactly_once"
    persisted_click = PriorStep(
        action_type="click",
        description="Activate the grounded exact control: Continue",
        target_selector="#exact-control",
        value="Continue",
        execution_result="success",
        page_url=page.url,
        page_title=page.title,
    )

    response = _deterministic_observed_report_response(
        session_id="generic-assignment-postcondition",
        task="Activate Continue once. Verify fixture_state=dynamic_dialog_completed_exactly_once and stop.",
        page_context=page,
        prior_steps=[persisted_click],
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.suggested_actions == []
    assert response.report.answer == (
        'Verified that the requested state became '
        '"fixture_state=dynamic_dialog_completed_exactly_once".'
    )


def test_explicit_named_control_uses_unique_enabled_observed_target_without_planner() -> None:
    page = _page(
        "https://unfamiliar.example.test/workspace",
        [
            InteractiveElement(
                type="button",
                selector="#disabled-control",
                text="Continue",
                accessibility_name="Continue",
                visible=True,
                state={"disabled": True},
            ),
            InteractiveElement(
                type="button",
                selector="#exact-control",
                text="Continue",
                accessibility_name="Continue",
                visible=True,
                state={},
            ),
            InteractiveElement(
                type="button",
                selector="#continue-later",
                text="Continue later",
                accessibility_name="Continue later",
                visible=True,
                state={},
            ),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="generic-explicit-control",
        task="Activate the exact enabled control named Continue once.",
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "act"
    assert len(response.suggested_actions) == 1
    assert response.suggested_actions[0].target_selector == "#exact-control"
    assert response.suggested_actions[0].grounding["semantic_kind"] == "explicitly_named_control"


def test_explicit_named_download_preserves_observed_resource_identity() -> None:
    page = _page(
        "https://unfamiliar.example.test/downloads",
        [
            InteractiveElement(
                type="a",
                role="link",
                selector="#download-report",
                text="Download Report",
                accessibility_name="Download Report",
                href="https://unfamiliar.example.test/synthetic-download.txt",
                semantic_kind="download_control",
                download_filename="synthetic-download.txt",
                visible=True,
            ),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="generic-download-control",
        task="Activate the exact Download Report link once.",
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert action.target_selector == "#download-report"
    assert action.grounding["semantic_kind"] == "download_control"
    assert action.grounding["expected_download_filename"] == "synthetic-download.txt"
    assert action.grounding["expected_download_url"] == "https://unfamiliar.example.test/synthetic-download.txt"


def test_completed_download_reports_only_from_typed_file_evidence() -> None:
    page = _page("https://unfamiliar.example.test/downloads", [])
    completed = PriorStep(
        action_type="click",
        description="Activate the grounded exact control: Download Report",
        target_selector="#download-report",
        value="Download Report",
        execution_result="success",
        page_url=page.url,
        page_title=page.title,
        browser_evidence={
            "download_detected": True,
            "download_completed": True,
            "filename": "synthetic-download.txt",
            "mime_type": "text/plain",
            "size_bytes": 106,
        },
    )

    response = _deterministic_observed_report_response(
        session_id="generic-download-report",
        task="Download synthetic-download.txt and verify its completed filename, MIME type, and positive size.",
        page_context=page,
        prior_steps=[completed],
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert '"synthetic-download.txt"' in response.report.answer
    assert "text/plain" in response.report.answer
    assert "106 bytes" in response.report.answer


def test_natural_field_assignment_then_exact_control_advances_without_planner() -> None:
    page = _page(
        "https://unfamiliar.example.test/",
        [
            InteractiveElement(
                type="input",
                role="searchbox",
                selector="#query",
                text="",
                accessibility_name="Search",
                placeholder="Search",
                visible=True,
            ),
            InteractiveElement(
                type="button",
                selector="#run-search",
                accessibility_name="Search",
                text="Search",
                visible=True,
            ),
        ],
    )
    task = (
        "In the visible search field enter 'Browser automation', "
        "then activate the exact enabled Search control once."
    )

    fill_response = _deterministic_observed_control_response(
        session_id="natural-field-assignment",
        task=task,
        page_context=page,
        prior_steps=[],
    )
    assert fill_response is not None
    assert fill_response.suggested_actions[0].action_type == "fill"
    assert fill_response.suggested_actions[0].target_selector == "#query"
    assert fill_response.suggested_actions[0].value == "Browser automation"

    # A dynamically rendered text-entry control may share the submit control's
    # accessible name. Activation semantics must still prefer the unique button.
    page.interactive_elements.append(InteractiveElement(
        type="input",
        role="textbox",
        selector="#suggestion-filter",
        text="",
        accessibility_name="Search",
        visible=True,
    ))

    click_response = _deterministic_observed_control_response(
        session_id="natural-field-assignment",
        task=task,
        page_context=page,
        prior_steps=[PriorStep(
            action_type="fill",
            description="Fill the uniquely observed search field",
            target_selector="#query",
            value="Browser automation",
            execution_result="success",
            page_url=page.url,
            page_title=page.title,
        )],
    )
    assert click_response is not None
    assert click_response.suggested_actions[0].action_type == "click"
    assert click_response.suggested_actions[0].target_selector == "#run-search"
    assert click_response.suggested_actions[0].value == "Search"


def test_explicit_named_control_pauses_when_multiple_enabled_exact_targets_exist() -> None:
    page = _page(
        "https://unfamiliar.example.test/workspace",
        [
            InteractiveElement(type="button", selector="#continue-a", text="Continue", visible=True),
            InteractiveElement(type="button", selector="#continue-b", text="Continue", visible=True),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="generic-ambiguous-control",
        task='Click the button named "Continue".',
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert "multiple enabled controls" in response.clarification_question.lower()


def test_named_link_prefers_unique_exact_rendered_text_over_duplicate_title_fallbacks() -> None:
    page = _page(
        "https://docs.example.test/library/index.html",
        [
            InteractiveElement(
                type="a", role="link", selector="#top-next", text="next",
                accessibility_name="asyncio — Asynchronous I/O", visible=True,
                href="https://docs.example.test/library/asyncio.html",
            ),
            InteractiveElement(
                type="a", role="link", selector="#body-link", text="asyncio — Asynchronous I/O",
                accessibility_name="asyncio — Asynchronous I/O", visible=True,
                href="https://docs.example.test/library/asyncio.html",
            ),
            InteractiveElement(
                type="a", role="link", selector="#bottom-next", text="next",
                accessibility_name="asyncio — Asynchronous I/O", visible=True,
                href="https://docs.example.test/library/asyncio.html",
            ),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="generic-visible-text-preference",
        task='Activate the exact visible link named asyncio — Asynchronous I/O exactly once.',
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].action_type == "click"
    assert response.suggested_actions[0].target_selector == "#body-link"


def test_named_link_collapses_duplicate_visible_controls_with_same_verified_destination() -> None:
    destination = "https://docs.example.test/library/asyncio.html"
    page = _page(
        "https://docs.example.test/library/index.html",
        [
            InteractiveElement(
                type="a", role="link", selector="#next-topic", text="asyncio — Asynchronous I/O",
                accessibility_name="asyncio — Asynchronous I/O", visible=True, href=destination,
                bounding_box={"x": 20, "y": 200, "width": 175, "height": 18},
            ),
            InteractiveElement(
                type="a", role="link", selector="#body-link", text="asyncio — Asynchronous I/O",
                accessibility_name="asyncio — Asynchronous I/O", visible=True, href=destination,
                bounding_box={"x": 340, "y": 330, "width": 213, "height": 22},
            ),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="generic-effect-equivalent-links",
        task='Activate the exact visible link named asyncio — Asynchronous I/O exactly once.',
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].target_selector == "#body-link"


def test_named_link_keeps_same_label_with_different_destinations_ambiguous() -> None:
    page = _page(
        "https://unfamiliar.example.test/workspace",
        [
            InteractiveElement(
                type="a", role="link", selector="#personal", text="Dashboard",
                accessibility_name="Dashboard", visible=True,
                href="https://personal.example.test/dashboard",
            ),
            InteractiveElement(
                type="a", role="link", selector="#work", text="Dashboard",
                accessibility_name="Dashboard", visible=True,
                href="https://work.example.test/dashboard",
            ),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="generic-distinct-link-effects",
        task='Activate the exact visible link named Dashboard exactly once.',
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []


def test_compound_named_controls_advance_in_order_after_verified_prior_click() -> None:
    task = (
        "Activate the exact enabled control named Open review, then activate "
        "the exact enabled control named Continue."
    )
    prior = PriorStep(
        action_type="click",
        description="Activate the grounded exact control: Open review",
        target_selector="#open-review",
        value="Open review",
        execution_result="CDP click dispatched\n\nExecution: success\nVerification: verified",
        page_url="https://unfamiliar.example.test/workspace",
        page_title="Fixture",
    )
    page = _page(
        "https://unfamiliar.example.test/workspace",
        [
            InteractiveElement(type="button", selector="#open-review", text="Open review", visible=True),
            InteractiveElement(type="button", selector="#continue", text="Continue", visible=True),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="generic-control-sequence",
        task=task,
        page_context=page,
        prior_steps=[prior],
    )

    assert response is not None
    assert response.suggested_actions[0].target_selector == "#continue"
    assert response.suggested_actions[0].value == "Continue"


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


def test_attachment_grounding_ignores_existing_message_status_content() -> None:
    task = (
        "Open WhatsApp and open the exact chat named Ramesh Spc. "
        "Attach the approved file synthetic-day5.txt and verify its preview. Do not send anything."
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
                accessibility_name="Type a message to Ramesh Spc",
            ),
            InteractiveElement(
                type="div",
                selector='[data-testid="list-item-24"]',
                text="Existing attached document synthetic-day5.txt",
                visible=True,
                role="row",
                accessibility_name=(
                    "Ramesh Spc Yesterday Existing attached document synthetic-day5.txt "
                    "Download file and view document"
                ),
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

    control = _deterministic_observed_control_response(
        session_id="ignore-message-status",
        task=task,
        page_context=page,
        prior_steps=[],
    )

    assert control is not None
    assert control.suggested_actions[0].target_selector == 'button[aria-label="Attach"]'
    assert control.suggested_actions[0].grounding is not None
    assert control.suggested_actions[0].grounding["accessibility_name"] == "Attach"
    assert control.suggested_actions[0].grounding["role"] == "button"


def test_verified_cdp_menu_click_advances_to_new_content_kind_control() -> None:
    task = "Open the exact chat named Rahul, then attach the approved file synthetic-day5.txt."
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="div",
                selector='[data-testid="conversation-compose-box-input"]',
                text="",
                visible=True,
                role="textbox",
                accessibility_name="Type a message to Rahul",
            ),
            InteractiveElement(
                type="button",
                selector='button[aria-label="Attach"]',
                text="",
                visible=True,
                accessibility_name="Attach",
            ),
            InteractiveElement(
                type="button",
                selector='button[aria-label="Document"]',
                text="",
                visible=True,
                accessibility_name="Document",
            ),
        ],
    )
    opened_menu = PriorStep(
        action_type="click",
        description="Activate the observed content-insertion control",
        target_selector='button[aria-label="Attach"]',
        value=None,
        execution_result="CDP click dispatched via stable_selector grounding.",
    )

    control = _deterministic_observed_control_response(
        session_id="advance-after-cdp",
        task=task,
        page_context=page,
        prior_steps=[opened_menu],
    )

    assert control is not None
    action = control.suggested_actions[0]
    assert action.target_selector == 'button[aria-label="Document"]'
    assert action.content_insertion is not None
    assert action.content_insertion["stage"] == "select_bound_content"
    assert action.content_insertion["opens_native_chooser"] is True
    assert action.content_insertion["reveal_selector"] == 'button[aria-label="Attach"]'
    assert action.content_insertion["requested_filename"] == "synthetic-day5.txt"
    assert action.content_insertion["destination_entity"] == "Rahul"
    assert action.content_insertion["destination_url"] == "https://web.whatsapp.com/"
    assert action.content_insertion["expected_effect"] == "preview_then_send"


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
            "destination_url": "https://messaging.example.test/thread/123",
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
        "destination_url": "https://other.example.test/thread/123",
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
    selection.browser_evidence["destination_url"] = "https://messaging.example.test/thread/other"
    wrong_document = _deterministic_observed_report_response(
        session_id="wrong-document",
        task=(
            "Open the exact chat named Synthetic Recipient. Attach the file named synthetic-day4.txt. "
            "Do not send anything."
        ),
        page_context=page,
        prior_steps=[selection],
    )
    assert wrong_document is None

    selection.browser_evidence["destination_url"] = "https://messaging.example.test/thread/123"
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


def test_negative_login_constraint_never_selects_optional_login_control() -> None:
    page = _page(
        "https://code.example.test/acme/runner",
        [InteractiveElement(type="a", selector="#login", text="Sign in", visible=True, role="link")],
    )
    page.visible_text = "acme runner Sign in"

    response = _deterministic_observed_control_response(
        session_id="negative-login-constraint",
        task=(
            "Open the exact project named acme/runner and verify its identity. "
            "Do not sign in, submit, or change external data."
        ),
        page_context=page,
        prior_steps=[],
    )

    assert response is None


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
    insertion = response.suggested_actions[0].content_insertion
    assert insertion is not None
    assert insertion["destination_url"] == "http://127.0.0.1:5051/upload"
    assert insertion["destination_entity"] == "Fixture [http://127.0.0.1:5051/upload]"
    assert insertion["expected_effect"] == "selection_sends_immediately"


def test_content_insertion_effect_and_destination_are_provider_neutral() -> None:
    page = _page(
        "https://workspace.example.test/drafts/42?mode=edit",
        [InteractiveElement(type="input", input_type="file", selector="#file", text="", visible=True)],
    )
    page.title = "Synthetic Composer"
    task = 'Attach "synthetic-day5.txt" to the draft named "Client Review".'
    destination_url = "https://workspace.example.test/drafts/42?mode=edit"
    assert _content_insertion_destination_entity(task, page, destination_url) == "Client Review"
    assert _content_insertion_effect(task) == "structured_draft"


def test_structured_draft_opens_unique_semantic_composer_before_attachment() -> None:
    page = _page(
        "https://mail.example.test/workspace/#inbox",
        [
            InteractiveElement(
                type="button", role="button", selector="#new-item", text="Compose", visible=True,
                accessibility_name="Compose",
            ),
            InteractiveElement(
                type="input", role="searchbox", selector="#search", text="", visible=True,
                accessibility_name="Search mail",
            ),
        ],
    )
    response = _deterministic_observed_control_response(
        session_id="generic-draft-open",
        task=(
            'Create one new draft with subject "Synthetic preview". '
            'Attach "synthetic-day5.txt" and verify its preview. Do not send it.'
        ),
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert (action.action_type, action.target_selector) == ("click", "#new-item")
    assert action.grounding["semantic_kind"] == "draft_creation_trigger"
    assert action.content_insertion is None


def test_structured_draft_fills_unique_subject_before_attachment() -> None:
    page = _page(
        "https://mail.example.test/workspace/#drafts/17",
        [
            InteractiveElement(
                type="input", role="textbox", selector="#topic", text="", visible=True,
                accessibility_name="Subject", state={"value": ""},
            ),
            InteractiveElement(
                type="button", role="button", selector="#insert", text="Attach", visible=True,
                accessibility_name="Attach",
            ),
        ],
    )
    response = _deterministic_observed_control_response(
        session_id="generic-draft-subject",
        task=(
            'Create one new draft with subject "Synthetic preview". '
            'Attach "synthetic-day5.txt" and verify its preview. Do not send it.'
        ),
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert (action.action_type, action.target_selector, action.value) == (
        "fill", "#topic", "Synthetic preview",
    )
    assert action.grounding["semantic_kind"] == "draft_subject_field"
    assert action.content_insertion is None


def test_structured_draft_attaches_only_after_subject_is_observed() -> None:
    page = _page(
        "https://mail.example.test/workspace/#drafts/17",
        [
            InteractiveElement(
                type="input", role="textbox", selector="#topic", text="", visible=True,
                accessibility_name="Subject", state={"value": "Synthetic preview"},
            ),
            InteractiveElement(
                type="button", role="button", selector="#insert", text="Attach", visible=True,
                accessibility_name="Attach",
            ),
        ],
    )
    response = _deterministic_observed_control_response(
        session_id="generic-draft-attach",
        task=(
            'Create one new draft with subject "Synthetic preview". '
            'Attach "synthetic-day5.txt" and verify its preview. Do not send it.'
        ),
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert (action.action_type, action.target_selector) == ("click", "#insert")
    assert action.content_insertion is not None
    assert action.content_insertion["expected_effect"] == "structured_draft"


def test_content_insertion_ignores_unrelated_bare_more_and_add_controls() -> None:
    page = _page(
        "https://mail.example.test/workspace/#drafts/17",
        [
            InteractiveElement(
                type="input", role="textbox", selector="#topic", text="", visible=True,
                accessibility_name="Subject", state={"value": "Synthetic preview"},
            ),
            InteractiveElement(
                type="button", role="button", selector="#more-labels", text="More", visible=True,
                accessibility_name="More labels",
            ),
            InteractiveElement(
                type="button", role="button", selector="#add-contact", text="Add", visible=True,
                accessibility_name="Add contact",
            ),
            InteractiveElement(
                type="button", role="button", selector="#attach-files", text="", visible=True,
                accessibility_name="Attach files",
            ),
        ],
    )
    response = _deterministic_observed_control_response(
        session_id="generic-draft-ignore-broad-controls",
        task=(
            'Create one new draft with subject "Synthetic preview". '
            'Attach "synthetic-day5.txt" and verify its preview. Do not send it.'
        ),
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert action.target_selector == "#attach-files"
    assert action.grounding["accessibility_name"] == "Attach files"
    assert action.content_insertion is not None
    assert action.content_insertion["opens_native_chooser"] is True


def test_structured_draft_refuses_ambiguous_creation_controls() -> None:
    page = _page(
        "https://mail.example.test/workspace/#inbox",
        [
            InteractiveElement(type="button", role="button", selector="#personal", text="Compose", visible=True),
            InteractiveElement(type="button", role="button", selector="#shared", text="Compose", visible=True),
        ],
    )
    response = _deterministic_observed_control_response(
        session_id="generic-draft-ambiguous",
        task='Create a new draft with subject "Synthetic preview".',
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert "which account or composer" in response.clarification_question.casefold()


def test_repeated_composer_identity_and_punctuation_spacing_verify_one_destination() -> None:
    page = _page(
            "https://messages.example.test/thread/42",
            [
                InteractiveElement(
                    type="div", role="textbox", selector="#composer", text="", visible=True,
                    aria_label="Type a message to Ramu (Nanna)",
                    accessibility_name="Type a message to Ramu (Nanna) Type a message to Ramu (Nanna)",
                ),
                InteractiveElement(
                    type="button", role="button", selector="#attach", text="", visible=True,
                    aria_label="Attach", accessibility_name="Attach",
                ),
            ],
        )
    assert _exact_identity_key("Ramu(Nanna)") == _exact_identity_key("Ramu (Nanna)")
    assert _composer_destination_candidates([item.model_dump() for item in page.interactive_elements]) == ["Ramu (Nanna)"]
    response = _deterministic_observed_control_response(
        session_id="composer-duplicate-support",
        task='Open the exact chat named "Ramu(Nanna)" and attach the file "synthetic-day5.txt". Do not send it.',
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].target_selector == "#attach"


def test_conflicting_composer_identities_do_not_authorize_content_insertion() -> None:
    response = _deterministic_observed_control_response(
        session_id="composer-conflict",
        task='Open the exact chat named "Ramu (Nanna)" and attach the file "synthetic-day5.txt". Do not send it.',
        page_context=_page(
            "https://messages.example.test/thread/42",
            [
                InteractiveElement(
                    type="div", role="textbox", selector="#composer", text="", visible=True,
                    aria_label="Type a message to Ramu (Nanna)",
                    accessibility_name="Type a message to Different Person",
                ),
                InteractiveElement(
                    type="button", role="button", selector="#attach", text="", visible=True,
                    aria_label="Attach", accessibility_name="Attach",
                ),
            ],
        ),
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert "has not been verified" in response.analysis


def test_content_insertion_ignores_disabled_file_input_decoy() -> None:
    response = _deterministic_observed_control_response(
        session_id="upload-randomized",
        task='Attach the approved file "synthetic-day5.txt" and verify its preview without sending.',
        page_context=_page(
            "https://workspace.example.test/content",
            [
                InteractiveElement(
                    type="input", input_type="file", selector="#disabled-file", text="", visible=True,
                    state={"disabled": True},
                ),
                InteractiveElement(
                    type="input", input_type="file", selector="#approved-file", text="", visible=True,
                ),
            ],
        ),
        prior_steps=[],
    )

    assert response is not None
    assert response.suggested_actions[0].target_selector == "#approved-file"


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
    assert action.content_insertion is not None
    assert action.content_insertion["destination_url"] == "https://messaging.example.test/thread/123"
    assert action.content_insertion["expected_effect"] == "preview_then_send"


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
        'span[title="Teja Spc"]',
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


def test_whatsapp_missing_exact_result_waits_once_then_does_not_click() -> None:
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
    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].action_type == "wait"

    stopped = _deterministic_observed_control_response(
        session_id="wa",
        task=task,
        page_context=page,
        prior_steps=[
            PriorStep(
                action_type="fill",
                description="contact search",
                target_selector="#chat-search",
                value="Teja Spc",
                execution_result="success",
            ),
            PriorStep(
                action_type="wait",
                description="wait for results",
                target_selector="window",
                value="1000",
                execution_result="Waited 1000ms",
            ),
        ],
    )
    assert stopped is not None
    assert stopped.outcome_kind == "ask"
    assert stopped.suggested_actions == []
    assert "no exact visible match" in stopped.clarification_question.lower()


def test_explicit_first_chat_selects_first_visual_exact_match_without_changing_identity() -> None:
    task = (
        "Open WhatsApp and search for Ramu (Nanna) the first chat, then attach "
        "the approved file synthetic-day5.txt."
    )
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
                state={"value": "Ramu (Nanna)"},
            ),
            InteractiveElement(
                type="span",
                selector="#chat-result-name",
                text="Ramu (Nanna)",
                visible=True,
                accessibility_name="Ramu (Nanna)",
                bounding_box={"x": 120, "y": 200, "width": 140, "height": 24},
            ),
            InteractiveElement(
                type="span",
                selector="#message-result-name",
                text="Ramu (Nanna)",
                visible=True,
                accessibility_name="Ramu (Nanna)",
                bounding_box={"x": 120, "y": 700, "width": 140, "height": 24},
            ),
        ],
    )
    response = _deterministic_observed_control_response(
        session_id="wa-first-exact",
        task=task,
        page_context=page,
        prior_steps=[
            PriorStep(
                action_type="fill",
                description="contact search",
                target_selector="#chat-search",
                value="Ramu (Nanna)",
                execution_result="success",
            ),
            PriorStep(
                action_type="wait",
                description="wait for results",
                target_selector="window",
                value="1000",
                execution_result="success",
            ),
        ],
    )

    assert response is not None
    assert response.outcome_kind == "act"
    action = response.suggested_actions[0]
    assert action.action_type == "click"
    assert action.target_selector == "#chat-result-name"
    assert action.grounding is not None
    assert action.grounding["accessibility_name"] == "Ramu (Nanna)"


def test_whatsapp_current_search_value_is_not_treated_as_result_identity() -> None:
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
    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].action_type == "wait"


def test_whatsapp_changed_clarification_value_refills_same_search_control() -> None:
    task = 'Use the exact recipient named "RAHUL". Open WhatsApp and open the exact chat named "@old_handle".'
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
                state={"value": "@old_handle"},
            )
        ],
    )
    response = _deterministic_observed_control_response(
        session_id="wa-clarified",
        task=task,
        page_context=page,
        prior_steps=[
            PriorStep(
                action_type="fill",
                description="old contact search",
                target_selector="#chat-search",
                value="@old_handle",
                execution_result="success",
            )
        ],
    )

    assert response is not None
    assert response.suggested_actions[0].action_type == "fill"
    assert response.suggested_actions[0].value == "RAHUL"


def test_whatsapp_exact_row_outranks_highlighted_prefix_fragment() -> None:
    task = 'Open WhatsApp and open the exact chat named "Rahul". Do not send anything.'
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(type="span", selector='span[data-highlight="chat"]', text="Rahul", visible=True),
            InteractiveElement(type="span", selector='span[data-highlight="contact"]', text="Rahul", visible=True),
            InteractiveElement(
                type="div",
                selector='[data-testid="chat-result-rahul"]',
                text="Rahul 1:56 PM Recent message",
                visible=True,
                role="row",
            ),
            InteractiveElement(
                type="div",
                selector='[data-testid="contact-result-rahul-computers"]',
                text="Rahul Computers",
                visible=True,
                role="row",
            ),
        ],
    )

    response = _deterministic_observed_control_response(
        session_id="wa-exact-row",
        task=task,
        page_context=page,
        prior_steps=[],
    )

    assert response is not None
    action = response.suggested_actions[0]
    assert action.target_selector == '[data-testid="chat-result-rahul"]'
    assert action.grounding["accessibility_name"] == "Rahul"
    assert action.grounding["semantic_kind"] == "recipient"


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
                aria_label="Type a message to Teja Spc",
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


def test_whatsapp_wrong_open_destination_blocks_attachment_mutation() -> None:
    task = (
        'Open WhatsApp and open the exact chat named "@dhanunjaya_somireddy". '
        'Attach the approved file "synthetic-day5.txt" and send it.'
    )
    page = _page(
        "https://web.whatsapp.com/",
        [
            InteractiveElement(
                type="div",
                selector='div[aria-label="Type a message"]',
                text="",
                visible=True,
                role="textbox",
                aria_label="Type a message",
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
    )
    wrong_open = PriorStep(
        action_type="click",
        description="open result",
        target_selector='span[title="@dhanunjaya_somireddy"]',
        execution_result="success",
        browser_evidence={
            "adapter_exact_identity_verified": False,
            "adapter_exact_expected_name": "@dhanunjaya_somireddy",
            "adapter_exact_observed_name": "+91 97016 08432",
        },
    )

    response = _deterministic_observed_control_response(
        session_id="wa-wrong-destination",
        task=task,
        page_context=page,
        prior_steps=[wrong_open],
    )

    assert response is not None
    assert response.outcome_kind == "ask"
    assert response.suggested_actions == []
    assert "no content insertion or submission control was selected" in response.analysis.lower()


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


def test_observed_control_uses_unique_accessible_link_identity_without_field_concatenation() -> None:
    page_two = {
        "type": "a",
        "role": "link",
        "selector": 'a[aria-label="Page 2"]',
        "text": "Page 2",
        "aria_label": "Page 2",
        "accessibility_name": "Page 2",
        "visible": True,
    }
    next_page = {
        "type": "a",
        "role": "link",
        "selector": 'a[aria-label="Next page"]',
        "text": "Next",
        "aria_label": "Next page",
        "accessibility_name": "Next page",
        "visible": True,
    }

    assert _find_observed_control(
        [next_page, page_two], exact_labels=("2", "page 2")
    ) == page_two


def test_observed_control_rejects_ambiguous_exact_accessible_identity() -> None:
    duplicate_links = [
        {"type": "a", "role": "link", "selector": "#page-2-top", "text": "Page 2", "visible": True},
        {"type": "a", "role": "link", "selector": "#page-2-bottom", "aria_label": "Page 2", "visible": True},
    ]

    assert _find_observed_control(duplicate_links, exact_labels=("page 2",)) is None


def test_named_control_location_qualifier_preserves_child_frame_binding() -> None:
    response = _deterministic_observed_control_response(
        session_id="frame-control",
        task=(
            "Activate the exact enabled control named Continue inside the embedded workspace "
            "exactly once. Verify fixture_state=frame_continued_exactly_once"
        ),
        page_context=_page(
            "https://unfamiliar.example/frame-host",
            [
                InteractiveElement(
                    type="button",
                    selector="#frame-continue",
                    text="Continue",
                    visible=True,
                    role="button",
                    frame_id="chrome-frame:7",
                )
            ],
        ),
        prior_steps=[],
    )

    assert response is not None
    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].target_selector == "#frame-continue"
    assert response.suggested_actions[0].grounding["frame_id"] == "chrome-frame:7"


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


def test_public_form_does_not_receive_a_site_specific_core_procedure() -> None:
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

    assert _deterministic_observed_control_response(
        session_id="form", task=task, page_context=page, prior_steps=[]
    ) is None


def test_site_specific_confirmation_page_does_not_create_a_core_report() -> None:
    task = "Fill with test data, check validation errors, submit, and report whether submission succeeded."
    page = _page("https://www.selenium.dev/selenium/web/submitted-form.html", [])
    page = page.model_copy(update={"visible_text": "Form submitted Received!"})

    report = _deterministic_observed_report_response(session_id="form", task=task, page_context=page)

    assert report is None


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
