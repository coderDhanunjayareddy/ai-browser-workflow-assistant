from app.destination_resolution import decompose_destination_objectives, resolve_destination
from app.schemas.request import ContentBlock, PageContext, PriorStep


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


def test_unverifiable_destination_reports_meaningfully_without_navigation():
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
    assert result.outcome_kind == "report"
    assert result.sgv_verified is True
    assert result.suggested_actions == []
    assert "No candidate website was opened" in result.report.answer


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


def test_generic_page_control_is_not_misclassified_as_a_web_destination():
    assert decompose_destination_objectives("Open a synthetic folder") == []
    assert decompose_destination_objectives("Open the first result") == []
