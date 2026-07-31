from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentExecutionEvidence
from app.intent_dispatcher.registry import IntentOwnerRegistration, register_intent_executor, register_intent_owner
from app.intent_providers.common import execution_result


def register() -> None:
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="validation",
            capability="record_validation",
            dispatch_target="validation",
            reason="Validation is backend evidence validation over extracted artifacts.",
            matcher=lambda intent, _payload: intent in {"rank_records", "validate_records", "validate"},
        )
    )
    register_intent_executor("validation", execute)


def execute(context: ExecutionContext, directive: IntentDispatchDirective):
    if directive.intent == "rank_records":
        results = list((context.metadata.get("browser_intelligence") or {}).get("search_results") or [])
        evidence = IntentExecutionEvidence(
            evidence_id=f"{directive.intent}:{context.mission_id}:{len(results)}",
            source=directive.owner,
            kind=directive.capability,
            summary=f"Ranked {len(results)} observed result records.",
            payload={
                "ranked_result_count": len(results),
                "ranked_results": results,
            },
        )
        context.validation = evidence
        return execution_result(directive, status="succeeded", reason=evidence.summary, evidence=[evidence])

    snapshot = context.knowledge
    if snapshot is None:
        return execution_result(
            directive,
            status="blocked",
            reason="Validation intent requires knowledge extraction evidence.",
            blocking_reason="missing_knowledge_evidence",
        )
    valid_count = len([
        record for record in snapshot.extraction_records
        if bool(record.validation.get("valid"))
    ])
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}:{valid_count}",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Validated {valid_count} extracted records.",
        payload={
            "valid_record_count": valid_count,
            "extraction_record_count": len(snapshot.extraction_records),
            "completion_status": snapshot.completion_status,
        },
    )
    context.validation = evidence
    return execution_result(directive, status="succeeded", reason=evidence.summary, evidence=[evidence])
