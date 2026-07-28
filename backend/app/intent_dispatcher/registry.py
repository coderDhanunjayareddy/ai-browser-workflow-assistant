from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from app.intent_dispatcher.models import (
    ExecutionContext,
    ExecutionStatus,
    IntentDispatchDirective,
    IntentExecutionEvidence,
    IntentExecutionResult,
    IntentOwnership,
    IntentQueueResult,
)


Matcher = Callable[[str, dict[str, Any]], bool]
IntentExecutor = Callable[[ExecutionContext, IntentDispatchDirective], IntentExecutionResult]


@dataclass(frozen=True)
class IntentOwnerRegistration:
    provider_id: str
    capability: str
    dispatch_target: str
    reason: str
    matcher: Matcher
    browser_executable: bool = False

    @property
    def owner(self) -> str:
        return self.provider_id


class MissionExecutionQueue:
    def __init__(self, mission_id: str, items: Iterable[IntentDispatchDirective] | None = None) -> None:
        self.mission_id = mission_id
        self._items: deque[IntentDispatchDirective] = deque(items or [])

    def enqueue(self, item: IntentDispatchDirective) -> None:
        self._items.append(item)

    def extend(self, items: Iterable[IntentDispatchDirective]) -> None:
        for item in items:
            self.enqueue(item)

    def pop(self) -> IntentDispatchDirective | None:
        return self._items.popleft() if self._items else None

    def remaining(self) -> list[IntentDispatchDirective]:
        return list(self._items)


_REGISTRY: list[IntentOwnerRegistration] = []
_EXECUTORS: dict[str, IntentExecutor] = {}

_STOP_STATUSES: set[ExecutionStatus] = {
    "browser_action_required",
    "user_interaction_required",
    "waiting_external",
    "mission_completed",
    "failed",
    "blocked",
}


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
                owner=registration.provider_id,
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
    normalized = _normalize_intent(intent)
    ownership = resolve_intent_owner(normalized, payload)
    if ownership.owner == "unknown":
        return None
    target = next(
        (
            registration.dispatch_target
            for registration in _REGISTRY
            if registration.provider_id == ownership.owner
            and registration.capability == ownership.capability
        ),
        ownership.owner,
    )
    return IntentDispatchDirective(
        intent=normalized,
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
    context: ExecutionContext | dict[str, Any] | None = None,
) -> IntentExecutionResult:
    execution_context = _coerce_context(context, directive)
    executor = _EXECUTORS.get(directive.dispatch_target)
    if executor is None:
        return _execution_result(
            directive,
            status="failed",
            reason=f"No executor registered for dispatch target '{directive.dispatch_target}'.",
        )
    result = executor(execution_context, directive)
    directive.handled = result.success or result.status == "browser_action_required"
    execution_context.prior_evidence.extend(result.evidence)
    return result


def execute_intent_queue(
    *,
    mission_id: str,
    initial_intents: Iterable[IntentDispatchDirective],
    context: ExecutionContext | dict[str, Any] | None = None,
) -> IntentQueueResult:
    execution_context = _coerce_context(context, None, mission_id=mission_id)
    queue = MissionExecutionQueue(mission_id, initial_intents)
    executions: list[IntentExecutionResult] = []
    evidence: list[IntentExecutionEvidence] = []
    status: ExecutionStatus = "succeeded"
    reason = "Intent execution queue completed."
    browser_action: dict[str, Any] | None = None
    blocking_reason: str | None = None

    while True:
        directive = queue.pop()
        if directive is None:
            break
        result = execute_intent(directive, execution_context)
        executions.append(result)
        evidence.extend(result.evidence)
        queue.extend(result.next_intents)

        if result.status == "browser_action_required":
            browser_action = result.evidence[0].payload.get("browser_action") if result.evidence else None
        if result.status in _STOP_STATUSES:
            status = result.status
            reason = result.reason
            blocking_reason = result.blocking_reason
            break

    return IntentQueueResult(
        mission_id=mission_id,
        status=status,
        reason=reason,
        executions=executions,
        evidence=evidence,
        remaining_intents=queue.remaining(),
        browser_action=browser_action,
        blocking_reason=blocking_reason,
    )


def intent_dispatch_context() -> dict[str, Any]:
    return {
        "schema_version": "intent_dispatch.v2",
        "contract": (
            "Planner output expresses intent. Intent ownership and execution are "
            "resolved by the mission-scoped execution queue. Browser Control is "
            "a registered executor, not a parser special case."
        ),
        "registered_owners": [
            {
                "owner": registration.provider_id,
                "capability": registration.capability,
                "dispatch_target": registration.dispatch_target,
                "browser_executable": registration.browser_executable,
            }
            for registration in _REGISTRY
        ],
    }


def _coerce_context(
    context: ExecutionContext | dict[str, Any] | None,
    directive: IntentDispatchDirective | None,
    *,
    mission_id: str | None = None,
) -> ExecutionContext:
    if isinstance(context, ExecutionContext):
        return context
    data = dict(context or {})
    resolved_mission_id = str(
        mission_id
        or data.get("mission_id")
        or data.get("session_id")
        or (directive.payload.get("session_id") if directive is not None else "")
        or ""
    )
    return ExecutionContext(
        mission_id=resolved_mission_id,
        task=str(data.get("task") or ""),
        page_context=data.get("page_context"),
        prior_steps=list(data.get("prior_steps") or []),
        runtime_state=data.get("runtime_state") or data.get("runtime_state_snapshot"),
        entity_graph=data.get("entity_graph"),
        browser_intelligence=data.get("browser_intelligence"),
        knowledge=data.get("knowledge") or data.get("knowledge_snapshot"),
        validation=data.get("validation"),
        mission_plan=data.get("mission_plan"),
        success_criteria=data.get("success_criteria"),
        completion_state=data.get("completion_state") or data.get("mission_completion_snapshot"),
        phase_state=data.get("phase_state") or data.get("orchestrator_snapshot"),
        kernel_state=data.get("kernel_state") or data.get("kernel_snapshot"),
        prior_evidence=list(data.get("prior_evidence") or []),
        metadata=dict(data.get("metadata") or {}),
    )


def _normalize_intent(intent: str) -> str:
    return str(intent or "").strip().lower().replace("-", "_")


def _intent_in(*names: str) -> Matcher:
    normalized = {_normalize_intent(name) for name in names}
    return lambda intent, _payload: intent in normalized


def _execution_result(
    directive: IntentDispatchDirective,
    *,
    status: ExecutionStatus,
    reason: str,
    evidence: list[IntentExecutionEvidence] | None = None,
    next_intents: list[IntentDispatchDirective] | None = None,
    blocking_reason: str | None = None,
) -> IntentExecutionResult:
    return IntentExecutionResult(
        intent=directive.intent,
        owner=directive.owner,
        capability=directive.capability,
        dispatch_target=directive.dispatch_target,
        status=status,
        reason=reason,
        evidence=list(evidence or []),
        next_intents=list(next_intents or []),
        blocking_reason=blocking_reason,
    )


def _browser_executor(context: ExecutionContext, directive: IntentDispatchDirective) -> IntentExecutionResult:
    action = dict(directive.payload)
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}:browser_action_required",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Browser Control must execute {directive.intent}.",
        payload={"browser_action": action},
    )
    return _execution_result(
        directive,
        status="browser_action_required",
        reason=f"Browser action required: {directive.intent}.",
        evidence=[evidence],
        blocking_reason="browser_control_required",
    )


def _knowledge_extraction_executor(context: ExecutionContext, directive: IntentDispatchDirective) -> IntentExecutionResult:
    if not context.mission_id or not context.task or context.page_context is None:
        return _execution_result(
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
        return _execution_result(
            directive,
            status="blocked",
            reason="Knowledge Extraction pipeline is not enabled for this runtime.",
            blocking_reason="executor_disabled",
        )
    context.knowledge = snapshot

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
            "completion_status": snapshot.completion_status,
            "missing_artifacts": snapshot.missing_artifacts,
        },
    )
    next_intents: list[IntentDispatchDirective] = []
    if directive.capability == "field_extraction":
        validation = dispatch_intent(intent="validate_records", payload={"source_intent": directive.intent})
        completion = dispatch_intent(intent="evaluate_completion", payload={"source_intent": directive.intent})
        next_intents = [intent for intent in (validation, completion) if intent is not None]
    return _execution_result(
        directive,
        status="succeeded",
        reason=f"{directive.owner} executed {directive.intent}.",
        evidence=[evidence],
        next_intents=next_intents,
    )


def _validation_executor(context: ExecutionContext, directive: IntentDispatchDirective) -> IntentExecutionResult:
    snapshot = context.knowledge
    if snapshot is None:
        return _execution_result(
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
    return _execution_result(directive, status="succeeded", reason=evidence.summary, evidence=[evidence])


def _mission_completion_executor(context: ExecutionContext, directive: IntentDispatchDirective) -> IntentExecutionResult:
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
        return _execution_result(
            directive,
            status="blocked",
            reason="Mission Completion Controller is not enabled for this runtime.",
            blocking_reason="executor_disabled",
        )
    context.completion_state = snapshot
    status: ExecutionStatus = "mission_completed" if getattr(snapshot, "workflow_result", None) is not None else "succeeded"
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
    return _execution_result(directive, status=status, reason=snapshot.reason, evidence=[evidence])


def _runtime_state_executor(context: ExecutionContext, directive: IntentDispatchDirective) -> IntentExecutionResult:
    snapshot = context.runtime_state
    if snapshot is None:
        return _execution_result(
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
    return _execution_result(directive, status="succeeded", reason=evidence.summary, evidence=[evidence])


def _orchestrator_executor(context: ExecutionContext, directive: IntentDispatchDirective) -> IntentExecutionResult:
    snapshot = context.phase_state
    if snapshot is None:
        return _execution_result(
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
    return _execution_result(directive, status="succeeded", reason=evidence.summary, evidence=[evidence])


def _register_defaults() -> None:
    browser_actions = (
        "click",
        "fill",
        "scroll",
        "navigate",
        "wait",
        "select_option",
        "choose_date",
        "hover",
        "keyboard_shortcut",
        "open_new_tab",
        "switch_tab",
        "close_tab",
        "focus_existing_tab",
    )
    for action in browser_actions:
        register_intent_owner(
            IntentOwnerRegistration(
                provider_id="browser_control",
                capability=action,
                dispatch_target="browser_control",
                reason=f"Browser Control owns browser action {action}.",
                matcher=_intent_in(action),
                browser_executable=True,
            )
        )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="knowledge_extraction",
            capability="page_reading",
            dispatch_target="knowledge_extraction_pipeline",
            reason="Reading page content is backend knowledge work.",
            matcher=_intent_in("read_page", "read"),
        )
    )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="knowledge_extraction",
            capability="field_extraction",
            dispatch_target="knowledge_extraction_pipeline",
            reason="Field extraction is backend semantic work over observed page content.",
            matcher=_intent_in("extract_fields", "extract", "structured_extraction"),
        )
    )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="knowledge_extraction",
            capability="knowledge_synthesis",
            dispatch_target="knowledge_extraction_pipeline",
            reason="Knowledge synthesis is backend artifact computation.",
            matcher=_intent_in("synthesize_knowledge", "synthesize_report", "synthesize"),
        )
    )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="validation",
            capability="record_validation",
            dispatch_target="validation",
            reason="Validation is backend evidence validation over extracted artifacts.",
            matcher=_intent_in("validate_records", "validate"),
        )
    )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="mission_completion",
            capability="completion_evaluation",
            dispatch_target="mission_completion_controller",
            reason="Mission completion is evaluated from success criteria and evidence.",
            matcher=_intent_in("evaluate_completion", "mark_complete", "complete"),
        )
    )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="execution_orchestrator",
            capability="phase_continuation",
            dispatch_target="execution_orchestrator",
            reason="Deterministic phase continuation is owned by Execution Orchestrator.",
            matcher=_intent_in("continue_phase", "next_phase_item"),
        )
    )
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="runtime_state_manager",
            capability="runtime_state_update",
            dispatch_target="runtime_state_manager",
            reason="Runtime bindings and progress updates are owned by Runtime State Manager.",
            matcher=_intent_in("update_runtime_state", "bind_resource", "record_progress"),
        )
    )

    register_intent_executor("browser_control", _browser_executor)
    register_intent_executor("knowledge_extraction_pipeline", _knowledge_extraction_executor)
    register_intent_executor("validation", _validation_executor)
    register_intent_executor("mission_completion_controller", _mission_completion_executor)
    register_intent_executor("runtime_state_manager", _runtime_state_executor)
    register_intent_executor("execution_orchestrator", _orchestrator_executor)


_register_defaults()
