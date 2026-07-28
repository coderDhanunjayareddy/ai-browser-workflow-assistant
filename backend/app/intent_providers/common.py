from __future__ import annotations

from app.intent_dispatcher.models import (
    ExecutionStatus,
    IntentDispatchDirective,
    IntentExecutionEvidence,
    IntentExecutionResult,
)


def execution_result(
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
