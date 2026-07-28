from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentExecutionEvidence
from app.intent_dispatcher.registry import IntentOwnerRegistration, register_intent_executor, register_intent_owner
from app.intent_providers.common import execution_result


def register() -> None:
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="mission_completion",
            capability="completion_evaluation",
            dispatch_target="mission_completion_controller",
            reason="Mission completion is evaluated from success criteria and evidence.",
            matcher=lambda intent, _payload: intent in {"evaluate_completion", "mark_complete", "complete"},
        )
    )
    register_intent_executor("mission_completion_controller", execute)


def execute(context: ExecutionContext, directive: IntentDispatchDirective):
    from app.mission_completion import observe_mission_completion

    snapshot = observe_mission_completion(
        session_id=context.mission_id,
        task=context.task,
        knowledge_snapshot=context.knowledge,
        phase_state=context.phase_state,
        runtime_state=context.runtime_state,
        execution_state=context.kernel_state,
    )
    if snapshot is None:
        return execution_result(
            directive,
            status="blocked",
            reason="Mission Completion Controller is not enabled for this runtime.",
            blocking_reason="executor_disabled",
        )
    context.completion_state = snapshot
    status = "mission_completed" if getattr(snapshot, "workflow_result", None) is not None else "succeeded"
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Mission Completion evaluated criteria: {snapshot.decision}.",
        payload={
            "decision": str(snapshot.decision),
            "status": str(snapshot.status),
            "reason": snapshot.reason,
            "confidence": snapshot.confidence,
        },
    )
    return execution_result(directive, status=status, reason=snapshot.reason, evidence=[evidence])
