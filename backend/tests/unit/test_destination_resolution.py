from app.destination_resolution import decompose_destination_objectives, resolve_destination
from app.schemas.request import ContentBlock, InteractiveElement, PageContext, PriorStep


def page(url: str = "chrome://newtab/", *, links: list[tuple[str, str]] | None = None) -> PageContext:
    return PageContext(
        url=url,
        title="Search" if "google.com/search" in url else "New Tab",
        metadata={},
        interactive_elements=[],
        content_blocks=[ContentBlock(text=title, selector=f"a:nth-child({index})", href=href)
                        for index, (title, href) in enumerate(links or [], start=1)],
        headings=[],
        selected_text="",
        visible_text="\n".join(title for title, _ in links or []),
        images=[],
    )


def successful_navigation(url: str) -> PriorStep:
    return PriorStep(
        action_type="navigate",
        description=f"Open {url}",
        target_selector=None,
        value=url,
        execution_result="success: navigation verified",
        page_url=url,
        page_title="Loaded",
    )


def failed_navigation(url: str) -> PriorStep:
    return PriorStep(
        action_type="navigate",
        description=f"Open {url}",
        target_selector=None,
        value=url,
        execution_result="navigation timed out and failed",
        page_url="chrome://newtab/",
        page_title="New Tab",
    )


def internally_rejected_navigation(url: str) -> PriorStep:
    return PriorStep(
        action_type="navigate",
        description=f"Open {url}",
        target_selector=None,
        value=url,
        execution_result="failure: Execution message has an invalid canonical action contract.",
        page_url="chrome://newtab/",
        page_title="New Tab",
    )


def terminal_navigation(url: str, result: str) -> PriorStep:
    return PriorStep(
        action_type="navigate",
        description=f"Open {url}",
        target_selector=None,
        value=url,
        execution_result=result,
        page_url="chrome://newtab/",
        page_title="New Tab",
    )


def media_step(action_type: str, description: str, value: str, result: str = "success") -> PriorStep:
    return PriorStep(
        action_type=action_type,
        description=description,
        target_selector="#target",
        value=value,
        execution_result=result,
        page_url="https://www.youtube.com/",
        page_title="YouTube",
    )


def youtube_page(url: str, elements: list[InteractiveElement]) -> PageContext:
    return PageContext(
        url=url,
        title="YouTube",
        metadata={},
        interactive_elements=elements,
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="Search Home Music",
        images=[],
    )


def test_natural_language_known_application_resolves_without_supplied_url():
    result = resolve_destination(
        session_id="s1",
        task="Play Telugu music on YouTube",
        page_context=page(),
    )

    assert result is not None
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value == "https://www.youtube.com/"


def test_explicit_privileged_url_stops_without_search_or_navigation_substitute():
    for unsafe in ("chrome://settings", "edge://extensions", "about:config", "file:///private.txt"):
        result = resolve_destination(
            session_id=f"privileged-{unsafe.split(':', 1)[0]}",
            task=f"Open {unsafe} and change nothing.",
            page_context=page(),
        )

        assert result is not None
        assert result.outcome_kind == "report"
        assert result.suggested_actions == []
        assert unsafe in result.report.answer
        assert "no search substitute" in result.analysis.lower()
        assert "no privileged url" in result.report.claim.lower()


def test_capability_only_task_on_browser_owned_page_requests_destination_instead_of_waiting():
    result = resolve_destination(
        session_id="missing-mail-destination",
        task=(
            'Create a new mail draft with subject "Synthetic attachment preview test". '
            'Attach the approved synthetic file and do not send anything.'
        ),
        page_context=page(),
    )

    assert result is not None
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []
    assert "which website or application" in result.clarification_question.lower()
    assert "account" in result.clarification_question.lower()
    assert "no page action was dispatched" in result.analysis.lower()


def test_media_adapter_uses_visible_controls_then_verified_media_element():
    search_field = InteractiveElement(
        type="input", selector='input[name="search_query"]', text="Search", placeholder="Search", visible=True,
    )
    search_button = InteractiveElement(
        type="button", selector='button[aria-label="Search"]', text="Search", aria_label="Search", visible=True,
    )
    home = youtube_page("https://www.youtube.com/", [search_field, search_button])

    fill = resolve_destination(session_id="media-flow", task="Play Telugu music on YouTube", page_context=home)
    assert fill is not None
    assert fill.suggested_actions[0].action_type == "fill"
    assert fill.suggested_actions[0].target_selector == 'input[name="search_query"]'
    assert fill.suggested_actions[0].value == "Telugu music"

    filled_step = media_step("fill", 'Enter media query "Telugu music" in the visible YouTube search field', "Telugu music")
    submit = resolve_destination(
        session_id="media-flow", task="Play Telugu music on YouTube", page_context=home, prior_steps=[filled_step],
    )
    assert submit is not None
    assert submit.suggested_actions[0].action_type == "keyboard_shortcut"
    assert submit.suggested_actions[0].target_selector == 'input[name="search_query"]'
    assert submit.suggested_actions[0].value == "Enter"

    results = youtube_page(
        "https://www.youtube.com/results?search_query=Telugu+music",
        [
            InteractiveElement(
                type="a", selector='a.thumbnail[href="/watch?v=synthetic"]', text="4:57 4:57 Now playing",
                href="https://www.youtube.com/watch?v=synthetic", visible=True,
            ),
            InteractiveElement(
                type="a", selector='a.title[href="/watch?v=synthetic"]', text="Telugu music result",
                href="https://www.youtube.com/watch?v=synthetic", visible=True,
            ),
        ],
    )
    open_result = resolve_destination(
        session_id="media-flow", task="Play Telugu music on YouTube", page_context=results,
        prior_steps=[filled_step, media_step("keyboard_shortcut", "Submit media search", "Enter")],
    )
    assert open_result is not None
    assert open_result.suggested_actions[0].action_type == "click"
    assert open_result.suggested_actions[0].target_selector == 'a#video-title[href*="v=synthetic"]'
    assert open_result.suggested_actions[0].grounding == {
        "accessibility_name": "Telugu music result",
        "role": "link",
        "semantic_kind": "navigation_result",
        "expected_url_path": "/watch",
    }

    watch = youtube_page("https://www.youtube.com/watch?v=synthetic", [])
    play = resolve_destination(
        session_id="media-flow", task="Play Telugu music on YouTube", page_context=watch,
        prior_steps=[filled_step, media_step("click", "Open the first visible YouTube result", "")],
    )
    assert play is not None
    assert play.suggested_actions[0].action_type == "media_control"
    assert play.suggested_actions[0].target_selector == "video"

    complete = resolve_destination(
        session_id="media-flow", task="Play Telugu music on YouTube", page_context=watch,
        prior_steps=[media_step("media_control", "Start playback", '{"operation":"play"}', "Media play completed.")],
    )
    assert complete is not None
    assert complete.outcome_kind == "report"
    assert complete.sgv_verified is True


def test_compound_task_preserves_completed_gmail_and_opens_youtube_in_new_tab():
    task = "Open Gmail and play Telugu music"
    initial = resolve_destination(session_id="s2", task=task, page_context=page())
    assert initial is not None
    assert initial.suggested_actions[0].value == "https://mail.google.com/"

    continued = resolve_destination(
        session_id="s2",
        task=task,
        page_context=page("https://mail.google.com/mail/u/0/#inbox"),
        prior_steps=[successful_navigation("https://mail.google.com/")],
    )
    assert continued is not None
    assert continued.suggested_actions[0].action_type == "open_new_tab"
    assert continued.suggested_actions[0].value == "https://www.youtube.com/"


def test_compound_explicit_urls_on_same_host_preserve_path_identity():
    first_url = "http://127.0.0.1:8765/frame-conformance-fixture.html"
    second_url = "http://127.0.0.1:8765/pagination-conformance-fixture.html"
    task = f"Open {first_url}. Then open {second_url} in a new tab."

    initial = resolve_destination(session_id="same-host-paths", task=task, page_context=page())
    assert initial is not None
    assert initial.suggested_actions[0].action_type == "navigate"
    assert initial.suggested_actions[0].value == first_url

    continued = resolve_destination(
        session_id="same-host-paths",
        task=task,
        page_context=page(first_url),
        prior_steps=[successful_navigation(first_url)],
    )
    assert continued is not None
    assert continued.suggested_actions[0].action_type == "open_new_tab"
    assert continued.suggested_actions[0].value == second_url


def test_explicit_url_identity_normalizes_only_trailing_slash_and_optional_fragment():
    objective = "Open https://example.com/workspace/#inbox"
    result = resolve_destination(
        session_id="explicit-fragment",
        task=objective,
        page_context=page("https://example.com/workspace/#inbox"),
        prior_steps=[successful_navigation("https://example.com/workspace/#inbox")],
    )
    assert result is None

    different_path = resolve_destination(
        session_id="explicit-fragment-path",
        task=objective,
        page_context=page("https://example.com/other/#inbox"),
        prior_steps=[successful_navigation("https://example.com/other/#inbox")],
    )
    assert different_path is not None
    assert different_path.suggested_actions[0].value == "https://example.com/workspace/#inbox"


def test_explicit_url_remains_authoritative_when_later_words_imply_a_default_application():
    url = "https://docs.python.org/3/library/ipc.html"
    task = (
        f"Open {url}. Activate the exact visible link named asyncio — Asynchronous I/O exactly once. "
        "Verify that the opened document identity is asyncio — Asynchronous I/O. "
        "Do not sign in, download, submit feedback, or change any external data."
    )

    objectives = decompose_destination_objectives(task)
    assert len(objectives) == 1
    assert objectives[0].explicit_url == url
    assert objectives[0].app_id is None

    completed = resolve_destination(
        session_id="explicit-url-with-document-word",
        task=task,
        page_context=page(url),
        prior_steps=[successful_navigation(url)],
    )

    # Destination Resolution must yield to exact-control grounding once the
    # explicit destination is reached; it must not reopen the URL in a new tab.
    assert completed is None


def test_completed_destinations_focus_one_observed_existing_tab_by_exact_title():
    first_url = "http://127.0.0.1:8765/frame-conformance-fixture.html"
    second_url = "http://127.0.0.1:8765/pagination-conformance-fixture.html"
    task = (
        f"Open {first_url}. Then open {second_url} in a new tab. "
        "Return to the original tab titled Neutral Framed Workspace and verify that exact title."
    )
    prior_steps = [
        successful_navigation(first_url),
        PriorStep(
            action_type="open_new_tab",
            description=f"Open {second_url}",
            value=second_url,
            execution_result="success: new tab loaded",
            page_url=second_url,
            page_title="Neutral Pagination Workspace",
        ),
    ]
    result = resolve_destination(
        session_id="focus-exact-title",
        task=task,
        page_context=PageContext(
            url=second_url, title="Neutral Pagination Workspace", metadata={},
            interactive_elements=[], content_blocks=[], headings=[], selected_text="", visible_text="", images=[],
        ),
        prior_steps=prior_steps,
        user_context=(
            "Tab Workspace\nActive: Neutral Pagination Workspace\nOpen Tabs:\n"
            "1. Neutral Pagination Workspace - active\n"
            "2. Neutral Framed Workspace - visited"
        ),
    )
    assert result is not None
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "focus_existing_tab"
    assert result.suggested_actions[0].value == "title:Neutral Framed Workspace"


def test_exact_requested_tab_title_reports_only_after_active_title_matches():
    result = resolve_destination(
        session_id="focus-title-complete",
        task="Return to the original tab titled Neutral Framed Workspace and verify that exact title.",
        page_context=PageContext(
            url="https://example.test/", title="Neutral Framed Workspace", metadata={},
            interactive_elements=[], content_blocks=[], headings=[], selected_text="", visible_text="", images=[],
        ),
        user_context="Tab Workspace\nActive: Neutral Framed Workspace",
    )
    assert result is not None
    assert result.outcome_kind == "report"
    assert result.sgv_verified is True
    assert result.goal_convergence is True


def test_compound_task_preserves_failed_gmail_attempt_and_continues_independent_media_objective():
    continued = resolve_destination(
        session_id="s2-blocked",
        task="Open Gmail and play Telugu music",
        page_context=page("https://workspace.google.com/intl/en-US/gmail/"),
        prior_steps=[failed_navigation("https://mail.google.com/")],
    )
    assert continued is not None
    assert continued.outcome_kind == "act"
    assert continued.suggested_actions[0].action_type == "open_new_tab"
    assert continued.suggested_actions[0].value == "https://www.youtube.com/"


def test_compound_media_completion_reports_partial_block_without_retrying_gmail():
    complete = resolve_destination(
        session_id="s2-partial",
        task="Open Gmail and play Telugu music",
        page_context=youtube_page("https://www.youtube.com/watch?v=synthetic", []),
        prior_steps=[
            failed_navigation("https://mail.google.com/"),
            media_step("media_control", "Start playback", '{"operation":"play"}', "Media play completed."),
        ],
    )
    assert complete is not None
    assert complete.outcome_kind == "report"
    assert complete.sgv_verified is True
    assert "Partially completed" in complete.report.answer
    assert "Gmail" in complete.report.answer
    assert '"Telugu music"' in complete.report.answer


def test_incompatible_constrained_application_pauses_with_clear_alternative():
    result = resolve_destination(
        session_id="s3",
        task="Play Telugu music inside Gmail",
        page_context=page(),
    )

    assert result is not None
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []
    assert "Gmail does not support media playback" in result.clarification_question
    assert "YouTube" in result.clarification_question

    approved = resolve_destination(
        session_id="s3",
        task="Play Telugu music inside Gmail",
        page_context=page(),
        user_context="Question: May I use YouTube instead?\nAnswer: yes",
    )
    assert approved is not None
    assert approved.outcome_kind == "act"
    assert approved.suggested_actions[0].value == "https://www.youtube.com/"


def test_unknown_named_destination_starts_evidence_search_instead_of_guessing_url():
    result = resolve_destination(
        session_id="s4",
        task="Open RBVRRIT college Portal",
        page_context=page(),
    )

    assert result is not None
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value.startswith("https://www.google.com/search?q=")
    assert "RBVRRIT" in result.suggested_actions[0].description


def test_blocked_google_discovery_uses_one_bing_fallback_in_same_tab():
    result = resolve_destination(
        session_id="s4-blocked-google",
        task="Open RBVRRIT college Portal",
        page_context=page("https://www.google.com/sorry/index?continue=search"),
        prior_steps=[successful_navigation("https://www.google.com/search?q=RBVRRIT")],
    )
    assert result is not None
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "navigate"
    assert result.suggested_actions[0].value.startswith("https://www.bing.com/search?q=")


def test_blocked_bounded_search_providers_stop_without_another_navigation():
    result = resolve_destination(
        session_id="s4-blocked-both",
        task="Open RBVRRIT college Portal",
        page_context=page("https://www.bing.com/turing/captcha/challenge"),
        prior_steps=[
            successful_navigation("https://www.google.com/search?q=RBVRRIT"),
            successful_navigation("https://www.bing.com/search?q=RBVRRIT"),
        ],
    )
    assert result is not None
    assert result.outcome_kind == "report"
    assert result.suggested_actions == []
    assert "No candidate website was opened" in result.report.answer
    assert "not repeated" in result.report.answer


def test_ambiguous_official_portal_candidates_require_clarification():
    result = resolve_destination(
        session_id="s5",
        task="Open RBVRRIT college Portal",
        page_context=page(
            "https://www.google.com/search?q=RBVRRIT+college+portal+official+portal",
            links=[
                ("RBVRRIT Official College Portal", "https://rbvrrit.com/portal"),
                ("RBVRRIT Official Student Portal", "https://rbvrrit.ac.in/student-portal"),
            ],
        ),
        prior_steps=[successful_navigation("https://www.google.com/search?q=RBVRRIT")],
    )

    assert result is not None
    assert result.outcome_kind == "ask"
    assert "multiple plausible destinations" in result.clarification_question
    assert "No candidate has been opened" in result.clarification_question

    selected = resolve_destination(
        session_id="s5",
        task="Open RBVRRIT college Portal",
        page_context=page(
            "https://www.google.com/search?q=RBVRRIT+college+portal+official+portal",
            links=[
                ("RBVRRIT Official College Portal", "https://rbvrrit.com/portal"),
                ("RBVRRIT Official Student Portal", "https://rbvrrit.ac.in/student-portal"),
            ],
        ),
        prior_steps=[successful_navigation("https://www.google.com/search?q=RBVRRIT")],
        user_context="Question: Which portal?\nAnswer: rbvrrit.ac.in",
    )
    assert selected is not None
    assert selected.outcome_kind == "act"
    assert selected.suggested_actions[0].value == "https://rbvrrit.ac.in/student-portal"


def test_one_high_confidence_public_destination_opens_automatically():
    result = resolve_destination(
        session_id="s6",
        task="Open Acme University portal",
        page_context=page(
            "https://www.google.com/search?q=Acme+University+official+portal",
            links=[
                ("Acme University Official Portal", "https://portal.acmeuniversity.edu/"),
                ("Unrelated directory", "https://directory.example/college-list"),
            ],
        ),
        prior_steps=[successful_navigation("https://www.google.com/search?q=Acme+University")],
    )

    assert result is not None
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].value == "https://portal.acmeuniversity.edu/"


def test_unverifiable_destination_requests_identifying_detail_without_navigation():
    result = resolve_destination(
        session_id="s7",
        task="Open ZQX Unknown College portal",
        page_context=page(
            "https://www.google.com/search?q=ZQX+Unknown+College+official+portal",
            links=[("A generic directory", "https://directory.example/unrelated")],
        ),
        prior_steps=[successful_navigation("https://www.google.com/search?q=ZQX")],
    )

    assert result is not None
    assert result.outcome_kind == "ask"
    assert result.suggested_actions == []
    assert "No candidate website was opened" in result.clarification_question
    assert "What city" in result.clarification_question


def test_failed_navigation_is_not_repeated_and_becomes_meaningful_terminal_report():
    result = resolve_destination(
        session_id="s8",
        task="Play Telugu music on YouTube",
        page_context=page(),
        prior_steps=[failed_navigation("https://www.youtube.com/")],
    )

    assert result is not None
    assert result.outcome_kind == "report"
    assert result.suggested_actions == []
    assert "stopped instead of repeating" in result.report.answer


def test_internal_navigation_rejection_is_not_misattributed_to_network_or_search_evidence():
    result = resolve_destination(
        session_id="s9",
        task="Open WhatsApp",
        page_context=page(),
        prior_steps=[internally_rejected_navigation("https://web.whatsapp.com/")],
    )

    assert result is not None
    assert result.outcome_kind == "report"
    assert result.suggested_actions == []
    assert "internal execution validation" in result.report.answer
    assert "network" in result.report.answer  # explicitly says it was not blamed
    assert "No verified destination" not in result.report.claim
    assert "Destination discovery" not in result.analysis


def test_terminal_navigation_failure_classes_stop_without_duplicate_actions():
    cases = [
        ("navigation timed out after the configured budget", "timed out", "navigation_network"),
        ("navigation had no effect and page was unchanged", "did not change", "navigation_no_effect"),
        ("authentication required; login required", "authentication is required", "navigation_auth"),
        ("policy blocked navigation pending confirmation", "safety policy", "navigation_policy"),
    ]
    for index, (failure, expected_answer, expected_category) in enumerate(cases, start=1):
        result = resolve_destination(
            session_id=f"failure-class-{index}",
            task="Open WhatsApp",
            page_context=page(),
            prior_steps=[terminal_navigation("https://web.whatsapp.com/", failure)],
        )

        assert result is not None
        assert result.outcome_kind == "report"
        assert result.suggested_actions == []
        assert expected_answer in result.report.answer
        assert result.sgv_verified is True
        assert result.goal_convergence is True
        assert expected_category in result.analysis or "recorded execution failure" in result.analysis


def test_generic_page_control_is_not_misclassified_as_a_web_destination():
    assert decompose_destination_objectives("Open a synthetic folder") == []
    assert decompose_destination_objectives("Open the first result") == []


def test_named_whatsapp_chat_is_left_to_page_planner_after_destination_resolution():
    task = (
        "Open WhatsApp and open the exact direct chat named Teja Spc. "
        "Do not type a message, attach a file, or send anything."
    )

    initial = resolve_destination(session_id="s10", task=task, page_context=page())
    assert initial is not None
    assert initial.outcome_kind == "act"
    assert initial.suggested_actions[0].value == "https://web.whatsapp.com/"

    continued = resolve_destination(
        session_id="s10",
        task=task,
        page_context=page("https://web.whatsapp.com/"),
        prior_steps=[successful_navigation("https://web.whatsapp.com/")],
    )
    assert continued is None


def test_named_chat_is_never_treated_as_an_unknown_website():
    objectives = decompose_destination_objectives("Open the exact direct chat named Teja Spc")
    assert objectives == []
