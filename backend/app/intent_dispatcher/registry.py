from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.intent_dispatcher.models import (
    IntentDispatchDirective,
    IntentExecutionEvidence,
    IntentExecutionResult,
    IntentOwnership,
)


Matcher = Callable[[str, dict[str, Any]], bool]
IntentExecutor = Callable[[IntentDispatchDirective, dict[str, Any]], IntentExecutionResult]


@dataclass(frozen=True)
class IntentOwnerRegistration:
    owner: str
    capability: str
    dispatch_target: str
    reason: str
    matcher: Matcher
    browser_executable: bool = False


_REGISTRY: list[IntentOwnerRegistration] = []
_EXECUTORS: dict[str, IntentExecutor] = {}


def register_intent_owner(registration: IntentOwnerRegistration) -> None:
    _REGISTRY.append(registration)


def register_intent_executor(dispatch_target: str, executor: IntentExecutor) -> None:
    _EXECUTORS[dispatch_target] = executor


def resolve_intent_owner(intent: str, payload: dict[str, Any] | None = None) -> IntentOwnership:
    normalized = _normalize_intent(intent)
    payload = payload or {}
    for registration in _REGISTRY:
        if registration.matcher(normalized, payload):
            return IntentOwnership(
                owner=registration.owner,  # type: ignore[arg-type]
                capability=registration.capability,
                reason=registration.reason,
                browser_executable=registration.browser_executable,
            )
    return IntentOwnership(
        owner="unknown",
        capability=normalized,
        reason=f"No runtime owner registered for planner intent '{intent}'.",
        browser_executable=False,
    )


def dispatch_intent(
    *,
    intent: str,
    payload: dict[str, Any] | None = None,
) -> IntentDispatchDirective | None:
    ownership = resolve_intent_owner(intent, payload)
    if ownership.owner == "unknown":
        return None
    target = next(
        (
            registration.dispatch_target
            for registration in _REGISTRY
            if registration.owner == ownership.owner
            and registration.capability == ownership.capability
        ),
        ownership.owner,
    )
    return IntentDispatchDirective(
        intent=_normalize_intent(intent),
        owner=ownership.owner,
        capability=ownership.capability,
        dispatch_target=target,
        browser_executable=ownership.browser_executable,
        reason=ownership.reason,
        payload=dict(payload or {}),
        handled=False,
    )


def execute_intent(
    directive: IntentDispatchDirective,
    context: dict[str, Any] | None = None,
) -> IntentExecutionResult:
    executor = _EXECUTORS.get(directive.dispatch_target)
    if executor is None:
        return IntentExecutionResult(
            intent=directive.intent,
            owner=directive.owner,
            capability=directive.capability,
            dispatch_target=directive.dispatch_target,
            success=False,
            reason=f"No executor registered for dispatch target '{directive.dispatch_target}'.",
            evidence=[],
        )
    result = executor(directive, dict(context or {}))
    directive.handled = result.success and bool(result.evidence)
    return result


def intent_dispatch_context() -> dict[str, Any]:
    return {
        "schema_version": "intent_dispatch.v1",
        "contract": (
            "Planner output expresses intent. Browser suggested_actions are "
            "browser-control only; backend semantic work is owned and routed by "
            "the runtime before it can reach Browser Control."
        ),
        "registered_owners": [
            {
                "owner": registration.owner,
                "capability": registration.capability,
                "dispatch_target": registration.dispatch_target,
                "browser_executable": registration.browser_executable,
            }
            for registration in _REGISTRY
        ],
    }


def _normalize_intent(intent: str) -> str:
    return str(intent or "").strip().lower().replace("-", "_")


def _intent_in(*names: str) -> Matcher:
    normalized = {_normalize_intent(name) for name in names}
    return lambda intent, _payload: intent in normalized


register_intent_owner(
    IntentOwnerRegistration(
        owner="knowledge_extraction",
        capability="page_reading",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Reading page content is backend knowledge work, not browser control.",
        matcher=_intent_in("read_page", "read"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="validation",
        capability="record_validation",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Validation is backend evidence validation over extracted artifacts.",
        matcher=_intent_in("validate_records", "validate"),
    )
)


def _knowledge_extraction_executor(
    directive: IntentDispatchDirective,
    context: dict[str, Any],
) -> IntentExecutionResult:
    session_id = str(context.get("session_id") or "")
    task = str(context.get("task") or "")
    page_context = context.get("page_context")
    current_phase = context.get("current_phase")
    if not session_id or not task or page_context is None:
        return _execution_result(
            directive,
            success=False,
            reason="Knowledge Extraction intent requires session_id, task, and page_context.",
        )

    from app.knowledge_extraction import observe_knowledge_pipeline

    snapshot = observe_knowledge_pipeline(
        session_id=session_id,
        task=task,
        page_context=page_context,
        current_phase=str(current_phase) if current_phase else None,
    )
    if snapshot is None:
        return _execution_result(
            directive,
            success=False,
            reason="Knowledge Extraction pipeline is not enabled for this runtime.",
        )

    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{session_id}:{len(snapshot.extraction_records)}",
        source=directive.owner,
        kind=directive.capability,
        summary=(
            "Knowledge Extraction executed intent "
            f"{directive.intent}: reads={len(snapshot.read_artifacts)}, "
            f"records={len(snapshot.extraction_records)}, "
            f"report={snapshot.report_artifact.id if snapshot.report_artifact else 'none'}."
        ),
        references=[
            artifact.id for artifact in snapshot.read_artifacts[-5:]
        ] + ([snapshot.report_artifact.id] if snapshot.report_artifact else []),
        payload={
            "read_artifact_count": len(snapshot.read_artifacts),
            "extraction_record_count": len(snapshot.extraction_records),
            "valid_record_count": len([
                record for record in snapshot.extraction_records
                if bool(record.validation.get("valid"))
            ]),
            "knowledge_artifact_id": snapshot.knowledge_artifact.id if snapshot.knowledge_artifact else None,
            "report_artifact_id": snapshot.report_artifact.id if snapshot.report_artifact else None,
            "completion_status": snapshot.completion_status,
            "missing_artifacts": snapshot.missing_artifacts,
        },
    )
    return _execution_result(
        directive,
        success=True,
        reason=f"{directive.owner} executed {directive.intent}.",
        evidence=[evidence],
    )


def _mission_completion_executor(
    directive: IntentDispatchDirective,
    context: dict[str, Any],
) -> IntentExecutionResult:
    snapshot = context.get("mission_completion_snapshot")
    if snapshot is None:
        return _execution_result(
            directive,
            success=False,
            reason="Mission Completion intent requires a completion snapshot.",
        )
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{getattr(snapshot, 'session_id', 'unknown')}",
        source="mission_completion",
        kind=directive.capability,
        summary=f"Mission Completion evaluated criteria: {snapshot.decision}.",
        references=[],
        payload={
            "decision": str(snapshot.decision),
            "status": str(snapshot.status),
            "reason": snapshot.reason,
            "confidence": snapshot.confidence,
        },
    )
    return _execution_result(directive, success=True, reason=snapshot.reason, evidence=[evidence])


def _runtime_state_executor(
    directive: IntentDispatchDirective,
    context: dict[str, Any],
) -> IntentExecutionResult:
    snapshot = context.get("runtime_state_snapshot")
    if snapshot is None:
        return _execution_result(
            directive,
            success=False,
            reason="Runtime State intent requires a runtime state snapshot.",
        )
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{getattr(snapshot, 'session_id', 'unknown')}",
        source="runtime_state_manager",
        kind=directive.capability,
        summary="Runtime State Manager provided current runtime state evidence.",
        payload={
            "tab_count": len(getattr(snapshot, "tabs", []) or []),
            "artifact_count": len(getattr(snapshot, "artifacts", []) or []),
            "focused_tab_id": getattr(snapshot, "focused_tab_id", None),
        },
    )
    return _execution_result(directive, success=True, reason=evidence.summary, evidence=[evidence])


def _orchestrator_executor(
    directive: IntentDispatchDirective,
    context: dict[str, Any],
) -> IntentExecutionResult:
    snapshot = context.get("orchestrator_snapshot")
    if snapshot is None:
        return _execution_result(
            directive,
            success=False,
            reason="Execution Orchestrator intent requires an orchestrator snapshot.",
        )
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{getattr(snapshot, 'session_id', 'unknown')}",
        source="execution_orchestrator",
        kind=directive.capability,
        summary=f"Execution Orchestrator owns active phase {snapshot.active_phase.name}.",
        payload={
            "active_phase": snapshot.active_phase.name,
            "artifact_counts": snapshot.artifacts.counts(),
        },
    )
    return _execution_result(directive, success=True, reason=evidence.summary, evidence=[evidence])


def _execution_result(
    directive: IntentDispatchDirective,
    *,
    success: bool,
    reason: str,
    evidence: list[IntentExecutionEvidence] | None = None,
) -> IntentExecutionResult:
    return IntentExecutionResult(
        intent=directive.intent,
        owner=directive.owner,
        capability=directive.capability,
        dispatch_target=directive.dispatch_target,
        success=success,
        reason=reason,
        evidence=list(evidence or []),
    )


register_intent_executor("knowledge_extraction_pipeline", _knowledge_extraction_executor)
register_intent_executor("mission_completion_controller", _mission_completion_executor)
register_intent_executor("runtime_state_manager", _runtime_state_executor)
register_intent_executor("execution_orchestrator", _orchestrator_executor)
register_intent_owner(
    IntentOwnerRegistration(
        owner="knowledge_extraction",
        capability="field_extraction",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Field extraction is backend semantic work over observed page content.",
        matcher=_intent_in("extract_fields", "extract", "structured_extraction"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="knowledge_extraction",
        capability="knowledge_synthesis",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Knowledge synthesis is backend artifact computation.",
        matcher=_intent_in("synthesize_knowledge", "synthesize_report", "synthesize"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="mission_completion",
        capability="completion_evaluation",
        dispatch_target="mission_completion_controller",
        reason="Mission completion is evaluated from success criteria and evidence.",
        matcher=_intent_in("evaluate_completion", "mark_complete", "complete"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="execution_orchestrator",
        capability="phase_continuation",
        dispatch_target="execution_orchestrator",
        reason="Deterministic phase continuation is owned by the Execution Orchestrator.",
        matcher=_intent_in("continue_phase", "next_phase_item"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="runtime_state_manager",
        capability="runtime_state_update",
        dispatch_target="runtime_state_manager",
        reason="Runtime bindings and progress updates are owned by Runtime State Manager.",
        matcher=_intent_in("update_runtime_state", "bind_resource", "record_progress"),
    )
)
