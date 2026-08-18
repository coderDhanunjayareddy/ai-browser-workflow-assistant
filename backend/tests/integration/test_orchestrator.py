import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from types import SimpleNamespace

from app.core.database import Base
from app.models.db import WorkflowSession
from app.models.db import MissionIntentRecord
from app.orchestrator.workflow_orchestrator import (
    WorkflowOrchestrator,
    _deterministic_interactive_state_response,
    _deterministic_knowledge_report_response,
    _deterministic_open_phase_response,
    _deterministic_read_phase_response,
)
from app.runtime_state_manager.entity_binding import register_entity
from app.schemas.intent import IntentEvidence
from app.schemas.request import ContentBlock, InteractiveElement, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, ReportOutcome, SuggestedAction


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "mission_blueprint_v1", "off")
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def page(url: str) -> PageContext:
    return PageContext(
        url=url,
        title="Application",
        interactive_elements=[
            InteractiveElement(
                type="button",
                text="Continue",
                selector="#continue",
                visible=True,
            )
        ],
        selected_text="",
        visible_text="Continue",
    )


def search_results_page(url: str = "https://www.bing.com/search?q=best+AI+browser+automation+tools+2026") -> PageContext:
    return PageContext(
        url=url,
        title="Search Results",
        interactive_elements=[],
        content_blocks=[
            ContentBlock(
                text="Browser Use - AI browser automation",
                selector="#result-1",
                href="https://browser-use.com/",
            ),
            ContentBlock(
                text="Skyvern - browser workflow automation",
                selector="#result-2",
                href="https://www.skyvern.com/",
            ),
        ],
        headings=["Search results"],
        selected_text="",
        visible_text="Browser Use https://browser-use.com/\nSkyvern https://www.skyvern.com/",
    )


def directory_page(url: str = "https://directory.example/page/1") -> PageContext:
    return PageContext(
        url=url,
        title="Example Directory",
        interactive_elements=[
            InteractiveElement(
                type="a",
                text="Acme Labs",
                selector="#acme",
                href="https://directory.example/acme",
                visible=True,
            ),
            InteractiveElement(
                type="a",
                text="Beta Systems",
                selector="#beta",
                href="https://directory.example/beta",
                visible=True,
            ),
            InteractiveElement(
                type="a",
                text="Next",
                selector="#next",
                href="https://directory.example/page/2",
                visible=True,
            ),
        ],
        content_blocks=[],
        headings=["Example Directory"],
        selected_text="",
        visible_text=(
            "Acme Labs Contact hello@acme.test Phone +1 555 123 4567\n"
            "Beta Systems Contact team@beta.test Phone +1 555 987 6543"
        ),
        images=[],
    )


def whatsapp_page() -> PageContext:
    return PageContext(
        url="https://web.whatsapp.com/",
        title="WhatsApp",
        interactive_elements=[
            InteractiveElement(
                type="div",
                text="",
                selector='div[role="textbox"][aria-label="Search or start new chat"]',
                visible=True,
                role="textbox",
                aria_label="Search or start new chat",
                accessibility_name="Search or start new chat",
            ),
            InteractiveElement(
                type="div",
                text="",
                selector='div[contenteditable="true"][aria-label="Type a message"]',
                visible=True,
                role="textbox",
                aria_label="Type a message",
                accessibility_name="Type a message",
            ),
            InteractiveElement(
                type="button",
                text="",
                selector='button[aria-label="Attach"]',
                visible=True,
                role="button",
                aria_label="Attach",
                accessibility_name="Attach",
            ),
        ],
        selected_text="",
        visible_text="Use WhatsApp on your computer Scan QR code Search or start new chat Type a message",
    )


def opened_source_steps(count: int = 5) -> list[PriorStep]:
    return [
        PriorStep(
            action_type="open_new_tab",
            description=f"Open ranked result {index}",
            target_selector="",
            value=f"https://tool{index}.example/",
            execution_result="success",
            page_url="https://www.bing.com/search?q=best+AI+browser+automation+tools+2026",
            page_title="Search Results",
        )
        for index in range(1, count + 1)
    ]


@pytest.mark.parametrize("url", [
    "https://spectropy.com/",
    "https://example.test/application",
])
def test_planning_is_domain_neutral(db_session, monkeypatch, url):
    captured = {}

    def fake_analyze(**kwargs):
        captured.update(kwargs)
        return AnalyzeResponse(
            session_id=kwargs["session_id"],
            analysis="Ready",
            suggested_actions=[],
        )

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("domain-neutral-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Complete the requested workflow",
        page_context=page(url),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.analysis == "Ready"
    assert captured["active_node"] is None
    assert captured["page_context"].url == url
    assert db_session.get(WorkflowSession, "domain-neutral-session").tab_url == url


def test_execution_result_does_not_trigger_site_recovery(db_session):
    session = WorkflowSession(id="execution-session", status="running")
    db_session.add(session)
    db_session.commit()

    orchestrator = WorkflowOrchestrator("execution-session", db_session)
    orchestrator.process_executed_step(
        action_type="click",
        selector="#continue",
        value="",
        success=False,
        execution_result="No visible change",
    )

    db_session.refresh(session)
    assert session.status == "action_failed"


def test_ledger_failure_does_not_alter_planner_output(db_session, monkeypatch):
    from app.core.config import settings
    from app.run_ledger import writer as writer_module

    monkeypatch.setattr(settings, "v3_run_ledger", "shadow")

    def fail_event_to_record(_event):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(writer_module, "event_to_record", fail_event_to_record)

    expected = AnalyzeResponse(
        session_id="ledger-planner-session",
        analysis="Planner output is unchanged",
        suggested_actions=[],
    )

    def fake_analyze(**_kwargs):
        return expected

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("ledger-planner-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Plan normally",
        page_context=page("https://example.test/?token=secret"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response is expected
    assert response.analysis == "Planner output is unchanged"
    assert response.outcome_kind == "act"


def test_legacy_planner_action_is_bridged_into_mission_ledger(db_session, monkeypatch):
    planned_action = SuggestedAction(
        action_id="act-legacy",
        action_type="click",
        target_selector="#continue",
        value=None,
        description="Click Continue",
        reasoning="Continue the workflow",
        confidence=0.8,
        safety_level="safe",
    )

    def fake_analyze(**kwargs):
        return AnalyzeResponse(
            session_id=kwargs["session_id"],
            analysis="Planner selected a browser action",
            suggested_actions=[planned_action],
        )

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("legacy-bridge-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Continue",
        page_context=page("https://example.test/application"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.intent_dispatch is not None
    assert response.intent_execution is not None
    assert response.intent_execution.status == "waiting_browser"
    assert len(response.suggested_actions) == 1
    assert response.suggested_actions[0].intent_id == response.intent_dispatch.intent_id
    assert response.suggested_actions[0].mission_id == "legacy-bridge-session"
    assert response.suggested_actions[0].action_type == "click"

    record = db_session.get(MissionIntentRecord, response.intent_dispatch.intent_id)
    assert record is not None
    assert record.mission_id == "legacy-bridge-session"
    assert record.provider == "browser_control"
    assert record.status == "WAITING_BROWSER"
    assert record.payload["action_id"] == "act-legacy"


def test_browser_control_navigate_url_in_selector_is_normalized_to_value(db_session, monkeypatch):
    planned_action = SuggestedAction(
        action_id="act-wa",
        action_type="navigate",
        target_selector="https://web.whatsapp.com/",
        value=None,
        description="Open WhatsApp Web",
        reasoning="Open the app entry point.",
        confidence=0.8,
        safety_level="safe",
    )

    def fake_analyze(**kwargs):
        return AnalyzeResponse(
            session_id=kwargs["session_id"],
            analysis="Planner selected app navigation",
            suggested_actions=[planned_action],
        )

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("wa-selector-normalize", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Open WhatsApp Web and detect whether login is required.",
        page_context=page("https://assistant.local/sidepanel"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.intent_execution is not None
    assert response.intent_execution.status == "waiting_browser"
    assert response.suggested_actions[0].action_type == "navigate"
    assert response.suggested_actions[0].target_selector == ""
    assert response.suggested_actions[0].value == "https://web.whatsapp.com/"


def test_collection_policy_next_page_action_is_bridged_into_mission_ledger(db_session, monkeypatch):
    def fake_analyze(**kwargs):
        return AnalyzeResponse(
            session_id=kwargs["session_id"],
            analysis="Need more directory pages.",
            suggested_actions=[],
        )

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("collection-policy-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Collect 20 entries from a multi-page directory with name, website, email, and phone.",
        page_context=directory_page(),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.suggested_actions
    action = response.suggested_actions[0]
    assert action.action_type == "navigate"
    assert action.value == "https://directory.example/page/2"
    assert action.intent_id is not None
    assert action.mission_id == "collection-policy-session"
    assert "CollectionPolicy continuation" in response.analysis

    record = db_session.get(MissionIntentRecord, action.intent_id)
    assert record is not None
    assert record.mission_id == "collection-policy-session"
    assert record.provider == "browser_control"
    assert record.status == "WAITING_BROWSER"
    assert record.payload["value"] == "https://directory.example/page/2"


def test_blueprint_active_analyze_bypasses_planner_and_queues_first_browser_intent(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service

    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))

    orchestrator = WorkflowOrchestrator("blueprint-runtime-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Open Google and search best AI browser automation tools 2026, open top 5, read each page, extract fields, and report.",
        page_context=page("about:blank"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.analysis.startswith("Mission Blueprint produced deterministic executable work")
    assert response.suggested_actions[0].action_type == "navigate"
    assert response.suggested_actions[0].value == "https://www.google.com"
    records = db_session.query(MissionIntentRecord).filter(MissionIntentRecord.mission_id == "blueprint-runtime-session").all()
    assert {record.blueprint_node_id for record in records} == {"open_search_engine"}
    assert records[0].status == "WAITING_BROWSER"


def test_blueprint_runtime_recovers_from_search_provider_challenge(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service

    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))

    orchestrator = WorkflowOrchestrator("blueprint-search-recovery-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Open Google Search and search for: `best AI browser automation tools 2026`. Open the top 5 relevant results and return a table.",
        page_context=page("https://www.google.com/sorry/index?continue=https%3A%2F%2Fwww.google.com%2Fsearch%3Fq%3Dbrowser"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].action_type == "navigate"
    assert response.suggested_actions[0].value == "https://www.bing.com/search?q=best+AI+browser+automation+tools+2026"
    assert "alternate search provider" in response.analysis


def test_blueprint_runtime_rotates_search_provider_after_bing_challenge(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service

    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))

    orchestrator = WorkflowOrchestrator("blueprint-bing-recovery-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Open Google Search and search for: `best AI browser automation tools 2026`. Open the top 5 relevant results and return a table.",
        page_context=PageContext(
            url="https://www.bing.com/search?q=best+AI+browser+automation+tools+2026&rdr=1",
            title="best AI browser automation tools 2026 - Search",
            interactive_elements=[],
            selected_text="",
            visible_text="One last step\nPlease solve the challenge below to continue",
        ),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].action_type == "navigate"
    assert response.suggested_actions[0].value == "https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"
    assert "alternate search provider" in response.analysis


def test_blueprint_active_explicit_url_collection_starts_at_source_url(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service

    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))
    prompt = """Open this public test directory page: https://quotes.toscrape.com/page/1/

Collect 20 entries from this multi-page directory.

Extract:
- quote text
- author
- tags
- source URL

Return a clean table only."""

    orchestrator = WorkflowOrchestrator("quotes-direct-runtime-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task=prompt,
        page_context=page("about:blank"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.analysis.startswith("Mission Blueprint produced deterministic executable work")
    assert response.suggested_actions[0].action_type == "navigate"
    assert response.suggested_actions[0].value == "https://quotes.toscrape.com/page/1/"
    records = db_session.query(MissionIntentRecord).filter(MissionIntentRecord.mission_id == "quotes-direct-runtime-session").all()
    assert {record.blueprint_node_id for record in records} == {"locate_source"}


def test_blueprint_completion_expands_next_ready_intent_without_analyze(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service, mission_ledger_service

    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))

    orchestrator = WorkflowOrchestrator("blueprint-progress-session", db_session)
    first = orchestrator.orchestrate_analysis(
        task="Open Google and search best AI browser automation tools 2026, open top 5, read each page, extract fields, and report.",
        page_context=page("about:blank"),
        prior_steps=[],
        supplemental_context="",
    )
    first_intent_id = first.suggested_actions[0].intent_id

    update = mission_ledger_service.update_intent(
        db_session,
        mission_id="blueprint-progress-session",
        intent_id=first_intent_id,
        outcome="success",
        evidence=IntentEvidence(
            success=True,
            message="Navigated to Google.",
            payload={
                "task": "Open Google and search best AI browser automation tools 2026, open top 5, read each page, extract fields, and report.",
                "page_context": page("https://www.google.com"),
            },
        ),
    )

    assert update.next_intent is not None
    assert update.next_intent.blueprint_node_id == "execute_search"
    assert update.next_intent.payload["action_type"] == "navigate"
    assert update.next_intent.payload["value"].startswith("https://www.google.com/search?q=")
    completed = (
        db_session.query(MissionIntentRecord)
        .filter(MissionIntentRecord.mission_id == "blueprint-progress-session")
        .filter(MissionIntentRecord.blueprint_node_id == "open_search_engine")
        .one()
    )
    assert completed.status == "COMPLETED"


def test_blueprint_collects_search_results_without_planner_after_search_recovery(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service

    monkeypatch.setattr(settings, "mission_blueprint_v1", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))

    prompt = "Open Google and search best AI browser automation tools 2026, open top 5, read each page, extract fields, and report."
    orchestrator = WorkflowOrchestrator("blueprint-serp-collect-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task=prompt,
        page_context=search_results_page(),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.analysis.startswith("Mission Blueprint collected search result candidates deterministically")
    assert response.suggested_actions == []
    assert response.intent_execution is not None
    assert response.intent_execution.status == "succeeded"
    completed = (
        db_session.query(MissionIntentRecord)
        .filter(MissionIntentRecord.mission_id == "blueprint-serp-collect-session")
        .filter(MissionIntentRecord.blueprint_node_id == "collect_serp_results")
        .one()
    )
    assert completed.status == "COMPLETED"


def test_read_phase_focuses_unread_source_without_planner(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service

    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))

    orchestrator = WorkflowOrchestrator("deterministic-read-focus-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Open the top 5 relevant results in new tabs. Read each page. Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=search_results_page(),
        prior_steps=opened_source_steps(5),
        supplemental_context="",
    )

    assert response.analysis.startswith("Execution Orchestrator continued READ phase deterministically")
    assert response.intent_execution is not None
    assert response.intent_execution.status in {"waiting_browser", "browser_action_required"}
    assert response.suggested_actions
    assert response.suggested_actions[0].action_type == "focus_existing_tab"
    assert response.suggested_actions[0].value == "url:https://tool1.example/"


def test_read_phase_after_observing_focused_source_moves_to_next_unread_without_planner(db_session, monkeypatch):
    from app.core.config import settings
    from app.services import ai_service

    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(ai_service, "analyze", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("planner should not run")))

    orchestrator = WorkflowOrchestrator("deterministic-read-page-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Open the top 5 relevant results in new tabs. Read each page. Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=PageContext(
            url="https://tool1.example/",
            title="Tool 1",
            metadata={},
            interactive_elements=[],
            content_blocks=[
                ContentBlock(
                    text="Tool 1 is an AI browser automation product. Pricing starts at $10. Limitation: beta integrations.",
                    selector="#main",
                    href=None,
                )
            ],
            headings=["Tool 1"],
            selected_text="",
            visible_text="Tool 1 is an AI browser automation product. Pricing starts at $10. Limitation: beta integrations.",
            images=[],
        ),
        prior_steps=opened_source_steps(5),
        supplemental_context="",
    )

    assert response.analysis.startswith("Execution Orchestrator continued READ phase deterministically")
    assert response.intent_execution is not None
    assert response.intent_execution.status in {"waiting_browser", "browser_action_required"}
    assert response.suggested_actions
    assert response.suggested_actions[0].action_type == "focus_existing_tab"
    assert response.suggested_actions[0].value == "url:https://tool2.example/"


def test_open_phase_continues_from_unopened_collected_source_without_planner():
    session_id = "open-phase-collected-source-continuation"
    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence.search_result_collection",
        title="First Source",
        canonical_url="https://sources.example/one",
        confidence=0.91,
        metadata={"rank": "1"},
    )
    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence.search_result_collection",
        title="Second Source",
        canonical_url="https://sources.example/two",
        confidence=0.9,
        metadata={"rank": "2"},
    )
    orchestrator_snapshot = SimpleNamespace(
        active_phase=SimpleNamespace(name="OPEN"),
        progress_ledger=SimpleNamespace(
            target_counts={"opened_pages": 2},
            current_counts={"opened_pages": 1},
        ),
        artifacts=SimpleNamespace(opened_pages=["https://sources.example/one"]),
    )

    response = _deterministic_open_phase_response(
        session_id=session_id,
        orchestrator_snapshot=orchestrator_snapshot,
    )

    assert response is not None
    assert response.outcome_kind == "act"
    assert response.suggested_actions[0].action_type == "open_new_tab"
    assert response.suggested_actions[0].value == "https://sources.example/two"
    assert "Planner fallback was not invoked" in response.analysis


def test_post_read_phase_still_focuses_unread_opened_source(db_session):
    orchestrator_snapshot = SimpleNamespace(
        active_phase=SimpleNamespace(name="EXTRACT"),
        progress_ledger=SimpleNamespace(
            target_counts={"opened_pages": 3},
            current_counts={"opened_pages": 3},
        ),
        artifacts=SimpleNamespace(
            opened_pages=[
                "https://tool1.example/",
                "https://tool2.example/",
                "https://tool3.example/",
            ]
        ),
    )
    knowledge_snapshot = SimpleNamespace(
        read_artifacts=[
            SimpleNamespace(canonical_url="https://tool1.example/"),
        ],
    )

    response = _deterministic_read_phase_response(
        db=db_session,
        session_id="post-read-phase-unread-source",
        task="Open the top 3 relevant results in new tabs. Read each page and return a table.",
        page_context=PageContext(
            url="https://tool1.example/",
            title="Tool 1",
            metadata={},
            interactive_elements=[],
            content_blocks=[],
            headings=[],
            selected_text="",
            visible_text="Tool 1",
            images=[],
        ),
        prior_steps=[],
        runtime_state_snapshot=None,
        knowledge_snapshot=knowledge_snapshot,
        mission_completion_snapshot=None,
        orchestrator_snapshot=orchestrator_snapshot,
    )

    assert response is not None
    assert response.suggested_actions
    assert response.suggested_actions[0].action_type == "focus_existing_tab"
    assert response.suggested_actions[0].value == "url:https://tool2.example/"


def test_read_phase_uses_prior_read_page_evidence_to_avoid_repeat_loop(db_session):
    snapshot = SimpleNamespace(
        active_phase=SimpleNamespace(name="READ"),
        artifacts=SimpleNamespace(opened_pages=["https://tool1.example/"]),
        progress_ledger=SimpleNamespace(target_counts={"opened_pages": 1}),
    )
    knowledge = SimpleNamespace(read_artifacts=[])
    prior = [
        PriorStep(
            action_type="read_page",
            description="Read opened source page: https://tool1.example/",
            target_selector="",
            value="",
            execution_result="Intent execution queue completed.",
            page_url="https://tool1.example/",
            page_title="Tool 1",
        )
    ]

    response = _deterministic_read_phase_response(
        db=db_session,
        session_id="read-prior-dedupe",
        task="Open the top 1 result and read each page.",
        page_context=page("https://tool1.example/"),
        prior_steps=prior,
        runtime_state_snapshot=None,
        knowledge_snapshot=knowledge,
        mission_completion_snapshot=None,
        orchestrator_snapshot=snapshot,
    )

    assert response is None


def test_read_phase_does_not_hijack_executable_whatsapp_validation(db_session):
    snapshot = SimpleNamespace(
        active_phase=SimpleNamespace(name="VALIDATE"),
        artifacts=SimpleNamespace(opened_pages=["https://web.whatsapp.com/"]),
        progress_ledger=SimpleNamespace(target_counts={"opened_pages": 1}),
    )

    response = _deterministic_read_phase_response(
        db=db_session,
        session_id="interactive-whatsapp-read-guard",
        task='Open the exact chat named "Teja Spc", attach the approved file, and send it once.',
        page_context=whatsapp_page(),
        prior_steps=[],
        runtime_state_snapshot=None,
        knowledge_snapshot=SimpleNamespace(read_artifacts=[]),
        mission_completion_snapshot=None,
        orchestrator_snapshot=snapshot,
    )

    assert response is None


def test_complete_knowledge_report_is_promoted_without_planner():
    knowledge_snapshot = SimpleNamespace(
        report_artifact=SimpleNamespace(
            id="report-complete",
            completion_status="complete",
            content="| Tool | Purpose | Pricing | Limitation | URL |\n| --- | --- | --- | --- | --- |\n| Example | Test | Free | Demo | https://example.test |",
        ),
        research_spec=SimpleNamespace(source_count=1),
        read_artifacts=[SimpleNamespace(canonical_url="https://example.test")],
        extraction_records=[SimpleNamespace(source_page="https://example.test")],
        completion_status={"source_count": True, "extract": True, "report": True},
    )

    response = _deterministic_knowledge_report_response(
        session_id="complete-knowledge-report",
        knowledge_snapshot=knowledge_snapshot,
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.backend_authoritative_report is True
    assert response.report is not None
    assert response.report.answer.startswith("| Tool | Purpose | Pricing | Limitation | URL |")


def test_complete_report_waits_for_required_opened_non_search_sources():
    knowledge_snapshot = SimpleNamespace(
        report_artifact=SimpleNamespace(
            id="report-too-early",
            completion_status="complete",
            content="| Tool | Purpose | Pricing | Limitation | URL |\n| --- | --- | --- | --- | --- |\n| Example | Test | Free | Demo | https://example.test |",
        ),
        research_spec=SimpleNamespace(source_count=5),
        read_artifacts=[
            SimpleNamespace(canonical_url="https://www.google.com/sorry/index"),
            SimpleNamespace(canonical_url="https://www.bing.com/search?q=tools"),
            SimpleNamespace(canonical_url="https://source1.example/"),
            SimpleNamespace(canonical_url="https://source2.example/"),
        ],
        extraction_records=[
            SimpleNamespace(source_page="https://source1.example/"),
            SimpleNamespace(source_page="https://source2.example/"),
        ],
        completion_status={"source_count": True, "extract": True, "report": True},
    )
    orchestrator_snapshot = SimpleNamespace(
        artifacts=SimpleNamespace(
            opened_pages=[
                "https://source1.example/",
                "https://source2.example/",
            ]
        )
    )

    response = _deterministic_knowledge_report_response(
        session_id="too-early-report",
        knowledge_snapshot=knowledge_snapshot,
        orchestrator_snapshot=orchestrator_snapshot,
    )

    assert response is None


def test_deterministic_interactive_state_reports_whatsapp_login_and_controls():
    snapshot = SimpleNamespace(
        artifacts=SimpleNamespace(opened_pages=["https://web.whatsapp.com/"]),
        active_phase=SimpleNamespace(name="VALIDATE"),
    )

    response = _deterministic_interactive_state_response(
        session_id="interactive-state",
        task="Open WhatsApp Web and detect whether logged in and contact field visible.",
        page_context=whatsapp_page(),
        orchestrator_snapshot=snapshot,
    )

    assert response is not None
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.goal_convergence is True
    assert response.backend_authoritative_report is True
    assert response.report is not None
    assert "Login/QR required | yes" in response.report.answer
    assert "Contact/search field visible | yes" in response.report.answer
    assert "Message field visible | yes" in response.report.answer
    assert "Attachment/file control visible | yes" in response.report.answer


def test_interactive_state_uses_editable_field_semantics_instead_of_chat_preview_text():
    snapshot = SimpleNamespace(
        artifacts=SimpleNamespace(opened_pages=["https://web.whatsapp.com/"]),
        active_phase=SimpleNamespace(name="VALIDATE"),
    )
    page = PageContext(
        url="https://web.whatsapp.com/",
        title="WhatsApp",
        interactive_elements=[
            InteractiveElement(type="button", text="Chats", selector='button[aria-label="Chats"]', visible=True, aria_label="Chats"),
            InteractiveElement(type="div", text="Message preview with a document", selector='[data-testid="list-item-6"]', visible=True, role="listitem"),
            InteractiveElement(
                type="input",
                text="Search or start a new chat",
                selector='input[aria-label="Search or start a new chat"]',
                visible=True,
                role="textbox",
                aria_label="Search or start a new chat",
                placeholder="Search or start a new chat",
            ),
        ],
        selected_text="",
        visible_text="WhatsApp Search or start a new chat",
    )

    response = _deterministic_interactive_state_response(
        session_id="interactive-state-semantic-fields",
        task="Open WhatsApp Web and detect the contact search, message, and attachment fields.",
        page_context=page,
        orchestrator_snapshot=snapshot,
    )

    assert response is not None and response.report is not None
    assert 'Contact/search field visible | yes | input[aria-label="Search or start a new chat"]' in response.report.answer
    assert "Message field visible | no | not observed" in response.report.answer
    assert "Attachment/file control visible | no | not observed" in response.report.answer


def test_interactive_state_does_not_hijack_executable_whatsapp_file_task():
    snapshot = SimpleNamespace(
        artifacts=SimpleNamespace(opened_pages=["https://web.whatsapp.com/"]),
        active_phase=SimpleNamespace(name="OPEN"),
    )

    response = _deterministic_interactive_state_response(
        session_id="interactive-file-task",
        task=(
            "Open WhatsApp Web. Find the exact contact named Rahul. Open the verified Rahul conversation. "
            "Attach the exact local file Project_Tracker_Status.xlsx. Verify the recipient and filename. "
            "Do not click Send until I explicitly approve."
        ),
        page_context=whatsapp_page(),
        orchestrator_snapshot=snapshot,
    )

    assert response is None


def test_ledger_failure_does_not_alter_execution_recording(db_session, monkeypatch):
    from app.core.config import settings
    from app.run_ledger import writer as writer_module

    monkeypatch.setattr(settings, "v3_run_ledger", "shadow")

    def fail_event_to_record(_event):
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(writer_module, "event_to_record", fail_event_to_record)

    session = WorkflowSession(id="ledger-execution-session", status="running")
    db_session.add(session)
    db_session.commit()

    orchestrator = WorkflowOrchestrator("ledger-execution-session", db_session)
    orchestrator.process_executed_step(
        action_type="click",
        selector="#continue",
        value="",
        success=True,
        execution_result="success",
    )

    db_session.refresh(session)
    assert session.status == "action_executed"


def test_semantic_graph_shadow_does_not_change_planner_request(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_semantic_graph", "shadow")
    captured = {}

    def fake_analyze(**kwargs):
        captured.update(kwargs)
        return AnalyzeResponse(
            session_id=kwargs["session_id"],
            analysis="Planner request unchanged",
            suggested_actions=[],
        )

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("semantic-shadow-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Complete the requested workflow",
        page_context=page("https://example.test/search?q=browser"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response.analysis == "Planner request unchanged"
    assert "semantic_graph" not in captured
    assert captured["page_context"].url == "https://example.test/search?q=browser"
    assert captured["compressed_context"] is not None


def test_context_packet_shadow_does_not_change_planner_request(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_semantic_graph", "shadow")
    monkeypatch.setattr(settings, "v3_context_packet", "shadow")
    captured = {}

    def fake_analyze(**kwargs):
        captured.update(kwargs)
        return AnalyzeResponse(
            session_id=kwargs["session_id"],
            analysis="Planner request still legacy",
            suggested_actions=[],
        )

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("context-packet-shadow-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Complete the requested workflow",
        page_context=page("https://example.test/search?q=browser"),
        prior_steps=[],
        supplemental_context="Workspace: active",
    )

    assert response.analysis == "Planner request still legacy"
    assert "context_packet" not in captured
    assert captured["supplemental_context"] == ""
    assert captured["compressed_context"]["active_goal"] == "Complete the requested workflow"


def test_intent_grounding_shadow_does_not_change_planner_response(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_semantic_graph", "shadow")
    monkeypatch.setattr(settings, "v3_context_packet", "shadow")
    monkeypatch.setattr(settings, "v3_intent_grounding", "shadow")
    expected_action = SuggestedAction(
        action_id="act-1",
        action_type="click",
        target_selector="#continue",
        value=None,
        description="Click Continue",
        reasoning="Continue the workflow",
        confidence=0.8,
        safety_level="safe",
    )
    expected = AnalyzeResponse(
        session_id="grounding-shadow-session",
        analysis="Planner response remains unchanged",
        suggested_actions=[expected_action],
    )

    def fake_analyze(**_kwargs):
        return expected

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("grounding-shadow-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Continue",
        page_context=page("https://example.test/application"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response is expected
    assert len(response.suggested_actions) == 1
    assert response.suggested_actions[0].intent_id is not None
    assert response.suggested_actions[0].target_selector == "#continue"
    assert response.outcome_kind == "act"


def test_mission_intelligence_shadow_does_not_change_planner_response(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_mission_intelligence", "shadow")
    expected = AnalyzeResponse(
        session_id="mission-shadow-session",
        analysis="Mission shadow state is advisory only",
        suggested_actions=[],
    )

    def fake_analyze(**_kwargs):
        return expected

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("mission-shadow-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Plan normally",
        page_context=page("https://example.test/application"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response is expected
    assert response.analysis == "Mission shadow state is advisory only"
    assert response.outcome_kind == "act"


def test_validation_shadow_preserves_report_sgv_compatibility(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_validation", "shadow")
    expected = AnalyzeResponse(
        session_id="validation-shadow-session",
        analysis="Report visible value",
        outcome_kind="report",
        suggested_actions=[],
        report=ReportOutcome(
            answer="Continue",
            claim="The requested value is visible on the page.",
        ),
    )

    def fake_analyze(**_kwargs):
        return expected

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("validation-shadow-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Tell me the visible button label",
        page_context=page("https://example.test/application"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response is expected
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.report is expected.report


def test_backend_authoritative_report_is_not_downgraded_by_page_local_sgv(db_session, monkeypatch):
    expected = AnalyzeResponse(
        session_id="backend-authoritative-report-session",
        analysis="Knowledge Extraction Pipeline produced the authoritative report artifact.",
        outcome_kind="report",
        suggested_actions=[],
        report=ReportOutcome(
            answer="| tool | purpose |\n| --- | --- |\n| Tool A | Multi-page evidence |",
            claim="Report generated from validated extraction artifacts.",
        ),
        sgv_verified=True,
        goal_convergence=True,
        backend_authoritative_report=True,
    )

    def fake_analyze(**_kwargs):
        return expected

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("backend-authoritative-report-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Produce a comparison table",
        page_context=page("https://example.test/current"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response is expected
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.goal_convergence is True
    assert response.backend_authoritative_report is True


def test_governance_shadow_does_not_change_planner_response(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_governance", "shadow")
    expected_action = SuggestedAction(
        action_id="act-1",
        action_type="click",
        target_selector="#continue",
        value=None,
        description="Click Continue",
        reasoning="Continue the workflow",
        confidence=0.8,
        safety_level="safe",
    )
    expected = AnalyzeResponse(
        session_id="governance-shadow-session",
        analysis="Governance shadow is advisory only",
        suggested_actions=[expected_action],
    )

    def fake_analyze(**_kwargs):
        return expected

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("governance-shadow-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Plan normally",
        page_context=page("https://example.test/application"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response is expected
    assert len(response.suggested_actions) == 1
    assert response.suggested_actions[0].intent_id is not None
    assert response.suggested_actions[0].target_selector == "#continue"
    assert response.outcome_kind == "act"


def test_learning_shadow_does_not_change_verified_report_response(db_session, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_learning", "shadow")
    expected = AnalyzeResponse(
        session_id="learning-shadow-session",
        analysis="Report visible value",
        outcome_kind="report",
        suggested_actions=[],
        report=ReportOutcome(
            answer="Continue",
            claim="The requested value is visible on the page.",
        ),
    )

    def fake_analyze(**_kwargs):
        return expected

    from app.services import ai_service
    monkeypatch.setattr(ai_service, "analyze", fake_analyze)

    orchestrator = WorkflowOrchestrator("learning-shadow-session", db_session)
    response = orchestrator.orchestrate_analysis(
        task="Tell me the visible button label",
        page_context=page("https://example.test/application"),
        prior_steps=[],
        supplemental_context="",
    )

    assert response is expected
    assert response.outcome_kind == "report"
    assert response.sgv_verified is True
    assert response.report is expected.report
