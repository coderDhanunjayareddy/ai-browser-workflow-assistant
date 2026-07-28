from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentExecutionEvidence
from app.intent_dispatcher.registry import IntentOwnerRegistration, register_intent_executor, register_intent_owner
from app.intent_providers.common import execution_result


def register() -> None:
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="runtime_state_manager",
            capability="runtime_state_update",
            dispatch_target="runtime_state_manager",
            reason="Runtime bindings and progress updates are owned by Runtime State Manager.",
            matcher=lambda intent, _payload: intent in {"update_runtime_state", "bind_resource", "record_progress"},
        )
    )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="execution_orchestrator",
            capability="phase_continuation",
            dispatch_target="execution_orchestrator",
            reason="Deterministic phase continuation is owned by Execution Orchestrator.",
            matcher=lambda intent, _payload: intent in {"continue_phase", "next_phase_item"},
        )
    )
    register_intent_executor("runtime_state_manager", execute_runtime_state)
    register_intent_executor("execution_orchestrator", execute_orchestrator)


def execute_runtime_state(context: ExecutionContext, directive: IntentDispatchDirective):
    snapshot = context.runtime_state
    if snapshot is None:
        return execution_result(
            directive,
            status="blocked",
            reason="Runtime State intent requires a runtime state snapshot.",
            blocking_reason="missing_runtime_state",
        )
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}",
        source=directive.owner,
        kind=directive.capability,
        summary="Runtime State Manager provided current runtime state evidence.",
        payload={
            "tab_count": len(getattr(snapshot, "tabs", []) or []),
            "artifact_count": len(getattr(snapshot, "artifacts", []) or []),
            "focused_tab_id": getattr(snapshot, "focused_tab_id", None),
        },
    )
    return execution_result(directive, status="succeeded", reason=evidence.summary, evidence=[evidence])


def execute_orchestrator(context: ExecutionContext, directive: IntentDispatchDirective):
    snapshot = context.phase_state
    if snapshot is None:
        return execution_result(
            directive,
            status="blocked",
            reason="Execution Orchestrator intent requires a phase snapshot.",
            blocking_reason="missing_phase_state",
        )
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Execution Orchestrator owns active phase {snapshot.active_phase.name}.",
        payload={
            "active_phase": snapshot.active_phase.name,
            "artifact_counts": snapshot.artifacts.counts(),
        },
    )
    return execution_result(directive, status="succeeded", reason=evidence.summary, evidence=[evidence])
