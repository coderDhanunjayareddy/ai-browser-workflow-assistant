from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentExecutionEvidence
from app.intent_dispatcher.registry import IntentOwnerRegistration, dispatch_intent, register_intent_executor, register_intent_owner
from app.intent_providers.common import execution_result


def register() -> None:
    for capability, intents, reason in (
        ("page_reading", ("read_page", "read"), "Reading page content is backend knowledge work."),
        (
            "field_extraction",
            ("extract_fields", "extract", "structured_extraction"),
            "Field extraction is backend semantic work over observed page content.",
        ),
        (
            "knowledge_synthesis",
            ("synthesize_knowledge", "synthesize_report", "generate_report", "synthesize"),
            "Knowledge synthesis is backend artifact computation.",
        ),
    ):
        register_intent_owner(
            IntentOwnerRegistration(
                provider_id="knowledge_extraction",
                capability=capability,
                dispatch_target="knowledge_extraction_pipeline",
                reason=reason,
                matcher=lambda candidate, _payload, expected={item.lower() for item in intents}: candidate in expected,
            )
        )
    register_intent_executor("knowledge_extraction_pipeline", execute)


def execute(context: ExecutionContext, directive: IntentDispatchDirective):
    if not context.mission_id or not context.task or context.page_context is None:
        return execution_result(
            directive,
            status="blocked",
            reason="Knowledge Extraction intent requires mission_id, task, and page_context.",
            blocking_reason="missing_execution_context",
        )

    from app.knowledge_extraction import observe_knowledge_pipeline

    phase_name = context.phase_state.active_phase.name if getattr(context.phase_state, "active_phase", None) else None
    snapshot = observe_knowledge_pipeline(
        session_id=context.mission_id,
        task=context.task,
        page_context=context.page_context,
        current_phase=phase_name,
    )
    if snapshot is None:
        return execution_result(
            directive,
            status="blocked",
            reason="Knowledge Extraction pipeline is not enabled for this runtime.",
            blocking_reason="executor_disabled",
        )
    context.knowledge = snapshot
    mission_result_id = None
    if directive.intent == "generate_report" and snapshot.report_artifact is not None:
        try:
            from app.core.database import SessionLocal
            from app.mission_result.service import MissionResultService

            with SessionLocal() as db:
                result = MissionResultService(db).persist_from_knowledge_snapshot(
                    mission_id=context.mission_id,
                    task=context.task,
                    knowledge_snapshot=snapshot,
                )
                mission_result_id = result.mission_result_id if result is not None else None
        except Exception:
            mission_result_id = None

    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}:{len(snapshot.extraction_records)}",
        source=directive.owner,
        kind=directive.capability,
        summary=(
            f"Knowledge Extraction executed {directive.intent}: "
            f"reads={len(snapshot.read_artifacts)}, records={len(snapshot.extraction_records)}, "
            f"report={snapshot.report_artifact.id if snapshot.report_artifact else 'none'}."
        ),
        references=[artifact.id for artifact in snapshot.read_artifacts[-5:]]
        + ([snapshot.report_artifact.id] if snapshot.report_artifact else []),
        payload={
            "read_artifact_count": len(snapshot.read_artifacts),
            "extraction_record_count": len(snapshot.extraction_records),
            "valid_record_count": len([
                record for record in snapshot.extraction_records
                if bool(record.validation.get("valid"))
            ]),
            "knowledge_artifact_id": snapshot.knowledge_artifact.id if snapshot.knowledge_artifact else None,
            "report_artifact_id": snapshot.report_artifact.id if snapshot.report_artifact else None,
            "mission_result_id": mission_result_id,
            "completion_status": snapshot.completion_status,
            "missing_artifacts": snapshot.missing_artifacts,
        },
    )
    next_intents: list[IntentDispatchDirective] = []
    for intent_name in directive.payload.get("next_intents", []):
        intent = dispatch_intent(intent=str(intent_name), payload={"source_intent": directive.intent})
        if intent is not None:
            next_intents.append(intent)
    if not next_intents and directive.capability == "field_extraction":
        for intent_name in ("validate_records", "evaluate_completion"):
            intent = dispatch_intent(intent=intent_name, payload={"source_intent": directive.intent})
            if intent is not None:
                next_intents.append(intent)
    return execution_result(
        directive,
        status="succeeded",
        reason=f"{directive.owner} executed {directive.intent}.",
        evidence=[evidence],
        next_intents=next_intents,
    )
