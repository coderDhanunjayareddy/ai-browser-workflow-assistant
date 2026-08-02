from __future__ import annotations

from datetime import datetime

from app.contracts.serialization import SerializationValidator
from app.intent_dispatcher.models import IntentDispatchDirective, IntentExecutionEvidence
from app.knowledge_extraction.models import KnowledgeArtifact, PageReadArtifact, ReportArtifact
from app.mission_result.models import MissionResult, MissionResultArtifact
from app.schemas.intent import IntentEvidence
from app.schemas.request import PageContext


def test_pydantic_round_trip_page_context_and_intent_evidence():
    validator = SerializationValidator()
    page = PageContext(
        url="https://example.test",
        title="Example",
        metadata={},
        interactive_elements=[],
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="Hello",
        images=[],
    )
    evidence = IntentEvidence(success=True, payload={"page_context": page.model_dump(mode="json")})

    assert validator.round_trip(page)["compatible"]
    assert validator.round_trip(evidence)["compatible"]


def test_intent_and_artifact_round_trips():
    validator = SerializationValidator()
    directive = IntentDispatchDirective(
        intent="navigate",
        owner="browser_control",
        capability="Browser",
        dispatch_target="browser_control",
        reason="Open page",
    )
    evidence = IntentExecutionEvidence(evidence_id="ev", source="provider", kind="test", summary="ok")
    read = PageReadArtifact(
        id="read_1",
        title="Example",
        canonical_url="https://example.test",
        headings=[],
        sections=[],
        paragraphs=["hello"],
        metadata={},
        tables=[],
        lists=[],
        forms=[],
        pricing_blocks=[],
        contact_blocks=[],
        navigation_context=[],
        timestamp_ms=1,
    )
    knowledge = KnowledgeArtifact(
        id="knowledge_1",
        artifact_type="comparison_table",
        records=[],
        content={"columns": ["Tool"], "rows": []},
        validation={},
        timestamp_ms=1,
    )
    report = ReportArtifact(
        id="report_1",
        format="markdown",
        content="| Tool |",
        structured={"columns": ["Tool"], "rows": []},
        source_knowledge_id="knowledge_1",
        completion_status="complete",
        timestamp_ms=1,
    )

    assert validator.round_trip(directive)["compatible"]
    assert validator.round_trip(evidence)["compatible"]
    assert validator.round_trip(read)["compatible"]
    assert validator.round_trip(knowledge)["compatible"]
    assert validator.round_trip(report)["compatible"]


def test_mission_result_round_trip():
    validator = SerializationValidator()
    now = datetime.utcnow()
    artifact = MissionResultArtifact(
        artifact_id="report_1",
        mission_result_id="mission_result_1",
        mission_id="mission_1",
        kind="markdown_report",
        title="Report",
        content_type="text/markdown",
        content="| Tool |",
        structured={"columns": ["Tool"], "rows": []},
        metadata={},
        created_at=now,
    )
    result = MissionResult(
        mission_result_id="mission_result_1",
        mission_id="mission_1",
        outcome="COMPLETE",
        final_answer="| Tool |",
        report_format="markdown",
        completion_reason="done",
        confidence=1.0,
        artifacts=[artifact],
        created_at=now,
        updated_at=now,
    )

    assert validator.round_trip(result)["compatible"]
