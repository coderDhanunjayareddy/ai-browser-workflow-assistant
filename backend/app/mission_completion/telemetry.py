from __future__ import annotations

from app.mission_completion.models import CompletionDecision, CompletionTelemetry


def build_telemetry(
    *,
    latency_ms: int,
    reason: str,
    decision: CompletionDecision,
    confidence: float,
    partial_count: int,
    report_generation_ms: int,
    planner_calls_saved: int,
) -> CompletionTelemetry:
    terminal = decision in {CompletionDecision.COMPLETE, CompletionDecision.PARTIAL_SUCCESS, CompletionDecision.FAILED}
    return CompletionTelemetry(
        completion_latency_ms=latency_ms,
        completion_reason=reason,
        completion_status=decision.value,
        planner_calls_saved=planner_calls_saved,
        completion_confidence=confidence,
        partial_completion_count=partial_count,
        retry_decisions=1 if decision == CompletionDecision.INCOMPLETE and planner_calls_saved == 0 else 0,
        report_generation_ms=report_generation_ms,
        workflow_exit_ms=latency_ms if terminal else 0,
    )
