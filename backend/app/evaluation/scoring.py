from __future__ import annotations

from collections import Counter

from app.contracts.ledger_events import LedgerEvent
from app.evaluation.models import EvaluationScoreDimensions, ExecutionMetrics


def clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def summarize_validation(events: list[LedgerEvent]) -> dict[str, object]:
    statuses: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    confidences: list[float] = []
    for event in events:
        if event.event_type != "validation.completed":
            continue
        payload = event.payload
        status = str(payload.get("validation_status") or "unknown")
        statuses[status] += 1
        if payload.get("failure_category"):
            failures[str(payload["failure_category"])] += 1
        if isinstance(payload.get("confidence"), int | float):
            confidences.append(float(payload["confidence"]))
    total = sum(statuses.values())
    satisfied = statuses.get("satisfied", 0)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "total": total,
        "satisfied": satisfied,
        "not_satisfied": statuses.get("not_satisfied", 0),
        "contradicted": statuses.get("contradicted", 0),
        "uncertain": statuses.get("uncertain", 0),
        "failure_categories": dict(sorted(failures.items())),
        "average_confidence": round(avg_confidence, 4),
    }


def summarize_governance(events: list[LedgerEvent]) -> dict[str, object]:
    decisions: Counter[str] = Counter()
    risk_levels: Counter[str] = Counter()
    approval_required = 0
    handoff_required = 0
    for event in events:
        if event.event_type != "governance.evaluated":
            continue
        payload = event.payload
        decisions[str(payload.get("policy_decision") or "unknown")] += 1
        risk_levels[str(payload.get("risk_level") or "unknown")] += 1
        approval_required += 1 if payload.get("approval_required") else 0
        handoff_required += 1 if payload.get("requires_handoff") else 0
    return {
        "total": sum(decisions.values()),
        "decisions": dict(sorted(decisions.items())),
        "risk_levels": dict(sorted(risk_levels.items())),
        "approval_required": approval_required,
        "handoff_required": handoff_required,
    }


def summarize_mission(events: list[LedgerEvent]) -> dict[str, object]:
    latest_mission = next(
        (event.payload for event in reversed(events) if event.event_type == "mission.updated"),
        {},
    )
    report_verified = any(
        event.event_type == "report.verified" and event.payload.get("sgv_verified")
        for event in events
    )
    failed = any(event.event_type in {"run.failed", "run.cancelled"} for event in events)
    completed = any(event.event_type == "run.completed" for event in events) or report_verified
    return {
        "state": latest_mission.get("state") or ("completed" if completed else "failed" if failed else "unknown"),
        "mode": latest_mission.get("mode") or "UNKNOWN",
        "completed": completed,
        "failed": failed,
        "report_verified": report_verified,
        "progress_summary": latest_mission.get("progress_summary") or "",
        "planner_iterations": latest_mission.get("planner_iterations", 0),
        "recovery_count": latest_mission.get("recovery_count", 0),
    }


def calculate_execution_metrics(events: list[LedgerEvent]) -> ExecutionMetrics:
    planner_turns = sum(1 for event in events if event.event_type == "planner.responded")
    execution_events = [event for event in events if event.event_type == "execution.completed"]
    successful = sum(1 for event in execution_events if event.payload.get("success"))
    failed = len(execution_events) - successful
    retry_count = failed
    recovery_count = sum(
        1
        for event in events
        if event.event_type in {"planner_recovery.prepared", "strategy_context.prepared"}
    )
    return ExecutionMetrics(
        planner_turns=planner_turns,
        browser_actions=len(execution_events),
        successful_actions=successful,
        failed_actions=failed,
        retry_count=retry_count,
        recovery_count=recovery_count,
        total_latency_ms=sum(_event_latency(event) for event in events),
        first_event_type=events[0].event_type if events else None,
        final_event_type=events[-1].event_type if events else None,
    )


def score_dimensions(
    *,
    validation_summary: dict[str, object],
    governance_summary: dict[str, object],
    mission_summary: dict[str, object],
    execution_metrics: ExecutionMetrics,
    events: list[LedgerEvent],
) -> EvaluationScoreDimensions:
    validation_total = int(validation_summary.get("total") or 0)
    governance_total = int(governance_summary.get("total") or 0)
    actions = execution_metrics.browser_actions
    failed_actions = execution_metrics.failed_actions
    blocked = int(
        (governance_summary.get("decisions") or {}).get("block", 0)  # type: ignore[union-attr]
    )
    handoffs = int(governance_summary.get("handoff_required") or 0)
    grounding_events = [event for event in events if event.event_type == "grounding.resolved"]
    grounding_resolved = sum(
        1 for event in grounding_events if event.payload.get("status") == "resolved"
    )
    return EvaluationScoreDimensions(
        mission_success=1.0 if mission_summary.get("completed") else 0.0,
        validation_success=(
            clamp(float(validation_summary.get("satisfied") or 0) / validation_total)
            if validation_total
            else 1.0
        ),
        grounding_quality=(
            clamp(grounding_resolved / len(grounding_events)) if grounding_events else 1.0
        ),
        retry_efficiency=clamp(1.0 - (execution_metrics.retry_count / max(actions, 1))),
        execution_efficiency=clamp(1.0 - (failed_actions / max(actions, 1))) if actions else 1.0,
        governance_compliance=(
            clamp(1.0 - ((blocked + handoffs) / governance_total)) if governance_total else 1.0
        ),
        replay_quality=1.0 if events == sorted(events, key=lambda event: (event.step_index, event.created_at, event.event_id)) else 0.5,
    )


def _event_latency(event: LedgerEvent) -> int:
    for key in ("latency_ms", "build_ms", "transition_ms"):
        value = event.payload.get(key)
        if isinstance(value, int | float):
            return int(value)
    return 0

