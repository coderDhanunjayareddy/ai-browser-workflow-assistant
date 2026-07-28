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
