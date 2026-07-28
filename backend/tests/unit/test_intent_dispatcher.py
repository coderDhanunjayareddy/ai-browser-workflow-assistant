from __future__ import annotations

import json

from app.intent_dispatcher import (
    dispatch_intent,
    execute_intent,
    execute_intent_queue,
    intent_dispatch_context,
    resolve_intent_owner,
)
from app.intent_dispatcher.models import ExecutionContext
from app.services.ai_service import parse_response


def test_extract_fields_is_owned_by_knowledge_extraction_not_browser_control():
    ownership = resolve_intent_owner("extract_fields")

    assert ownership.owner == "knowledge_extraction"
    assert ownership.capability == "field_extraction"
    assert ownership.browser_executable is False


def test_dispatch_context_exposes_registered_owners_without_browser_action_growth():
    context = intent_dispatch_context()

    capabilities = {
        (entry["owner"], entry["capability"])
        for entry in context["registered_owners"]
    }
    assert ("knowledge_extraction", "field_extraction") in capabilities
    assert ("browser_control", "navigate") in capabilities
    assert any(entry["browser_executable"] is True for entry in context["registered_owners"])


def test_parser_routes_backend_intent_without_adding_browser_action():
    raw = json.dumps({
        "analysis": "The page is ready for structured extraction.",
        "outcome_kind": "act",
        "suggested_actions": [
            {
                "action_id": "extract_1",
                "action_type": "extract_fields",
                "target_selector": "",
                "value": "tool,purpose,pricing,limitation,url",
                "description": "Extract requested comparison fields.",
                "reasoning": "The visible page content can be structured.",
                "confidence": 0.9,
                "safety_level": "safe",
            }
        ],
    })

    result = parse_response(raw, "intent-session")

    assert result.suggested_actions == []
    assert result.intent_dispatch is not None
    assert result.intent_dispatch.intent == "extract_fields"
    assert result.intent_dispatch.owner == "knowledge_extraction"
    assert result.intent_dispatch.browser_executable is False


def test_unknown_intent_still_fails_loudly():
    raw = json.dumps({
        "analysis": "Try an unknown capability.",
        "outcome_kind": "act",
        "suggested_actions": [
            {
                "action_id": "unknown_1",
                "action_type": "teleport_cursor",
                "target_selector": "",
                "value": None,
                "description": "Unknown operation.",
                "reasoning": "No provider owns this.",
                "confidence": 0.4,
                "safety_level": "safe",
            }
        ],
    })

    try:
        parse_response(raw, "intent-session")
    except ValueError as exc:
        assert "Unsupported action_type from AI: teleport_cursor" in str(exc)
    else:
        raise AssertionError("unknown planner intents must not be silently accepted")


def test_extract_fields_executor_invokes_knowledge_extraction_and_returns_evidence(monkeypatch):
    import app.knowledge_extraction as knowledge_extraction
    from app.knowledge_extraction.models import (
        ExtractionRecord,
        KnowledgeArtifact,
        KnowledgePipelineSnapshot,
        KnowledgePipelineTelemetry,
        PageReadArtifact,
        ReportArtifact,
    )

    def fake_observe_knowledge_pipeline(*, session_id, task, page_context, current_phase=None):
        read = PageReadArtifact(
            id="read_1",
            title="Tool Page",
            canonical_url="https://tool.example",
            headings=["Tool"],
            sections=[],
            paragraphs=["Pricing starts at $10."],
            metadata={},
            tables=[],
            lists=[],
            forms=[],
            pricing_blocks=["$10"],
            contact_blocks=[],
            navigation_context=[],
            timestamp_ms=1,
        )
        record = ExtractionRecord(
            id="rec_1",
            source_page="https://tool.example",
            producing_action="extract_fields",
            producing_phase=current_phase or "EXTRACT",
            extraction_type="comparison_fields",
            fields={"tool": "Tool", "pricing": "$10"},
            confidence=0.92,
            validation={"valid": True},
            timestamp_ms=2,
        )
        knowledge = KnowledgeArtifact(
            id="know_1",
            artifact_type="comparison_table",
            records=[record],
            content={"rows": [record.fields]},
            validation={"valid": True},
            timestamp_ms=3,
        )
        report = ReportArtifact(
            id="report_1",
            format="markdown",
            content="| tool | pricing |\n| --- | --- |\n| Tool | $10 |",
            structured={"rows": [record.fields]},
            source_knowledge_id="know_1",
            completion_status="complete",
            timestamp_ms=4,
        )
        return KnowledgePipelineSnapshot(
            schema_version="knowledge_extraction.v1",
            session_id=session_id,
            current_phase=current_phase,
            required_fields=["tool", "pricing"],
            read_artifacts=[read],
            extraction_records=[record],
            knowledge_artifact=knowledge,
            report_artifact=report,
            missing_artifacts=[],
            completion_status={"read": True, "extract": True, "synthesize": True, "report": True},
            telemetry=KnowledgePipelineTelemetry(
                page_read_ms=1,
                extraction_ms=1,
                synthesis_ms=1,
                report_ms=1,
                read_artifact_count=1,
                extraction_record_count=1,
                validation_failure_count=0,
                duplicate_count=0,
            ),
            replay=[],
        )

    monkeypatch.setattr(knowledge_extraction, "observe_knowledge_pipeline", fake_observe_knowledge_pipeline)
    directive = dispatch_intent(intent="extract_fields", payload={"value": "tool,purpose"})
    assert directive is not None

    result = execute_intent(
        directive,
        {
            "session_id": "intent-session",
            "task": "Extract tool pricing.",
            "page_context": object(),
            "current_phase": "EXTRACT",
        },
    )

    assert result.success is True
    assert directive.handled is True
    assert result.owner == "knowledge_extraction"
    assert result.evidence[0].kind == "field_extraction"
    assert result.evidence[0].payload["extraction_record_count"] == 1
    assert result.evidence[0].payload["report_artifact_id"] == "report_1"


def test_queue_chains_extract_validate_completion_without_planner_reentry(monkeypatch):
    import app.knowledge_extraction as knowledge_extraction
    import app.mission_completion as mission_completion
    from app.knowledge_extraction.models import (
        ExtractionRecord,
        KnowledgeArtifact,
        KnowledgePipelineSnapshot,
        KnowledgePipelineTelemetry,
        PageReadArtifact,
        ReportArtifact,
    )

    class CompletionSnapshot:
        session_id = "intent-session"
        decision = "COMPLETE"
        status = "COMPLETE"
        reason = "All criteria satisfied."
        confidence = 0.98
        workflow_result = object()

    def fake_observe_knowledge_pipeline(*, session_id, task, page_context, current_phase=None):
        read = PageReadArtifact(
            id="read_1",
            title="Tool Page",
            canonical_url="https://tool.example",
            headings=["Tool"],
            sections=[],
            paragraphs=["Pricing starts at $10."],
            metadata={},
            tables=[],
            lists=[],
            forms=[],
            pricing_blocks=["$10"],
            contact_blocks=[],
            navigation_context=[],
            timestamp_ms=1,
        )
        record = ExtractionRecord(
            id="rec_1",
            source_page="https://tool.example",
            producing_action="extract_fields",
            producing_phase=current_phase or "EXTRACT",
            extraction_type="comparison_fields",
            fields={"tool": "Tool", "pricing": "$10"},
            confidence=0.92,
            validation={"valid": True},
            timestamp_ms=2,
        )
        knowledge = KnowledgeArtifact(
            id="know_1",
            artifact_type="comparison_table",
            records=[record],
            content={"rows": [record.fields]},
            validation={"valid": True},
            timestamp_ms=3,
        )
        report = ReportArtifact(
            id="report_1",
            format="markdown",
            content="| tool | pricing |\n| --- | --- |\n| Tool | $10 |",
            structured={"rows": [record.fields]},
            source_knowledge_id="know_1",
            completion_status="complete",
            timestamp_ms=4,
        )
        return KnowledgePipelineSnapshot(
            schema_version="knowledge_extraction.v1",
            session_id=session_id,
            current_phase=current_phase,
            required_fields=["tool", "pricing"],
            read_artifacts=[read],
            extraction_records=[record],
            knowledge_artifact=knowledge,
            report_artifact=report,
            missing_artifacts=[],
            completion_status={"read": True, "extract": True, "synthesize": True, "report": True},
            telemetry=KnowledgePipelineTelemetry(
                page_read_ms=1,
                extraction_ms=1,
                synthesis_ms=1,
                report_ms=1,
                read_artifact_count=1,
                extraction_record_count=1,
                validation_failure_count=0,
                duplicate_count=0,
            ),
            replay=[],
        )

    monkeypatch.setattr(knowledge_extraction, "observe_knowledge_pipeline", fake_observe_knowledge_pipeline)
    monkeypatch.setattr(mission_completion, "observe_mission_completion", lambda **_kwargs: CompletionSnapshot())

    directive = dispatch_intent(intent="extract_fields", payload={"value": "tool,pricing"})
    assert directive is not None
    result = execute_intent_queue(
        mission_id="intent-session",
        initial_intents=[directive],
        context=ExecutionContext(
            mission_id="intent-session",
            task="Extract tool pricing.",
            page_context=object(),
        ),
    )

    assert [execution.intent for execution in result.executions] == [
        "extract_fields",
        "validate_records",
        "evaluate_completion",
    ]
    assert result.status == "mission_completed"
    assert len(result.evidence) == 3


def test_browser_control_is_registered_executor_and_stops_queue_for_browser():
    directive = dispatch_intent(intent="navigate", payload={"action_type": "navigate", "value": "https://example.test"})
    assert directive is not None
    assert directive.owner == "browser_control"

    result = execute_intent_queue(
        mission_id="browser-session",
        initial_intents=[directive],
        context=ExecutionContext(mission_id="browser-session", task="Open a page."),
    )

    assert result.status == "browser_action_required"
    assert result.browser_action is not None
    assert result.browser_action["value"] == "https://example.test"


def test_orchestrator_does_not_directly_mark_backend_intent_without_execution(monkeypatch):
    from app.core.config import settings
    from app.execution_orchestrator.engine import ExecutionOrchestrator
    from app.execution_orchestrator.models import (
        ArtifactRegistry,
        ExecutionBudgets,
        ExecutionOrchestratorSnapshot,
        OrchestratorTelemetry,
        PhaseState,
        ProgressLedger,
        RecoveryRoute,
    )
    from app.schemas.response import AnalyzeResponse

    monkeypatch.setattr(settings, "v48_execution_orchestrator", "active")
    directive = dispatch_intent(intent="extract_fields", payload={"value": "tool,purpose"})
    response = AnalyzeResponse(
        session_id="intent-session",
        analysis="Extract fields.",
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
    )
    snapshot = ExecutionOrchestratorSnapshot(
        schema_version="execution_orchestrator.v1",
        session_id="intent-session",
        workflow_category="research",
        phases=[],
        active_phase=PhaseState(name="EXTRACT", status="active"),
        progress_ledger=ProgressLedger(target_counts={}, current_counts={}, completed={}),
        artifacts=ArtifactRegistry(
            opened_pages=[],
            visited_urls=[],
            extracted_records=[],
            screenshots=[],
            uploaded_files=[],
            downloads=[],
            reports=[],
            tables=[],
            summaries=[],
            contacts=[],
            forms=[],
            generated_files=[],
        ),
        budgets=ExecutionBudgets(),
        transitions=[],
        recovery=RecoveryRoute(strategy="none", phase="EXTRACT", reason=""),
        replay=[],
        telemetry=OrchestratorTelemetry(
            phase_duration_ms=0,
            planner_turns_in_phase=0,
            phase_retries=0,
            transition_count=0,
            phase_failures=0,
            artifact_counts={},
            budget_consumption={},
            planner_rejection_count=0,
        ),
    )

    result = ExecutionOrchestrator().postprocess_response(response, snapshot)

    assert result.intent_dispatch is not None
    assert result.intent_dispatch.handled is False
    assert result.suggested_actions == []
