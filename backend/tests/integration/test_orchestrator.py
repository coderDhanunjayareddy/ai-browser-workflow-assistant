import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.db import WorkflowSession
from app.orchestrator.workflow_orchestrator import WorkflowOrchestrator
from app.schemas.request import InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, ReportOutcome, SuggestedAction


engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
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
    assert response.suggested_actions == [expected_action]
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
