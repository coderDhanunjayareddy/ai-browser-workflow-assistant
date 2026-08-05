from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.mission_result.persistence  # noqa: F401
from app.core.config import settings
from app.core.database import Base
from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective
from app.intent_providers.knowledge_executor import execute
from app.knowledge_extraction.engine import KnowledgeExtractionPipeline
from app.mission_result.service import MissionResultService
from app.schemas.request import ContentBlock, InteractiveElement, PageContext


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine)()


def _page(text: str, *, title: str = "Example Tool", url: str = "https://example.test/tool") -> PageContext:
    return PageContext(
        url=url,
        title=title,
        metadata={"description": "Example page"},
        interactive_elements=[
            InteractiveElement(type="a", selector="#pricing", text="Pricing", href=f"{url}/pricing", visible=True),
        ],
        content_blocks=[ContentBlock(selector="#main", text=text, href=url)],
        headings=[title],
        selected_text="",
        visible_text=text,
        images=[],
    )


def _enable_pipeline(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "shadow")


def test_mission_result_tables_are_additive():
    engine, db = _session()
    try:
        tables = set(inspect(engine).get_table_names())

        assert {"mission_results", "mission_result_artifacts", "mission_result_versions"} <= tables
    finally:
        db.close()
        engine.dispose()


def test_service_persists_result_from_completion_snapshot(monkeypatch):
    _enable_pipeline(monkeypatch)
    engine, db = _session()
    try:
        task = "Extract Tool, Purpose, Pricing, Limitation, URL and return a comparison table."
        snapshot = KnowledgeExtractionPipeline().observe(
            session_id="mission-result-service",
            task=task,
            page_context=_page("Example Tool automates browser workflows. Free plan available. Limited admin controls."),
            current_phase="REPORT",
        )

        result = MissionResultService(db).persist_from_knowledge_snapshot(
            mission_id="mission-result-service",
            task=task,
            knowledge_snapshot=snapshot,
        )

        assert result is not None
        assert result.final_answer.startswith("|")
        assert result.report_artifact_id
        assert result.knowledge_artifact_id
        assert any(artifact.kind == "markdown_report" for artifact in result.artifacts)
        assert MissionResultService(db).summary("mission-result-service").artifact_count >= 2
    finally:
        db.close()
        engine.dispose()


def test_service_does_not_complete_research_before_requested_source_count(monkeypatch):
    _enable_pipeline(monkeypatch)
    engine, db = _session()
    try:
        task = (
            "Search for: best AI browser automation tools 2026. "
            "Open the top 5 relevant results. "
            "Create a clean comparison table with columns: Tool, Purpose, Pricing, Limitation, URL."
        )
        snapshot = KnowledgeExtractionPipeline().observe(
            session_id="mission-result-source-gate",
            task=task,
            page_context=_page("Tool A automates browser workflows. Free plan available. Limited admin controls."),
            current_phase="REPORT",
        )

        result = MissionResultService(db).persist_from_knowledge_snapshot(
            mission_id="mission-result-source-gate",
            task=task,
            knowledge_snapshot=snapshot,
        )

        assert result is None
        assert snapshot.completion_status["source_count"] is False
    finally:
        db.close()
        engine.dispose()


def test_generate_report_executor_persists_mission_result(monkeypatch):
    _enable_pipeline(monkeypatch)

    calls = []

    class FakeService:
        def __init__(self, _db):
            pass

        def persist_from_knowledge_snapshot(self, *, mission_id, task, knowledge_snapshot):
            calls.append((mission_id, task, knowledge_snapshot.report_artifact.id))

            class Result:
                mission_result_id = "mission_result_123"

            return Result()

    monkeypatch.setattr("app.mission_result.service.MissionResultService", FakeService)

    directive = IntentDispatchDirective(
        intent_id="intent_generate",
        intent="generate_report",
        owner="knowledge_extraction",
        capability="knowledge_synthesis",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Generate final report.",
        payload={},
    )
    context = ExecutionContext(
        mission_id="mission-result-executor",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page("Example Tool automates browsers. Free plan available. Limited support."),
    )

    result = execute(context, directive)

    assert result.status == "succeeded"
    assert calls and calls[0][0] == "mission-result-executor"
    assert result.evidence[0].payload["mission_result_id"] == "mission_result_123"
    assert "content" not in result.evidence[0].payload
