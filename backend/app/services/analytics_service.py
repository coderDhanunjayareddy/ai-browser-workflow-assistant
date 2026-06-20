from collections import Counter
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.db import FailureRecord, WorkflowBudgetRecord, WorkflowCostMetric, WorkflowEvent, WorkflowSession
from app.schemas.analytics import CostMetrics, WorkflowAnalytics


def record_planner_call(db: Session, session_id: str, tokens: int, latency_ms: int) -> None:
    row = db.get(WorkflowCostMetric, session_id)
    if row is None:
        row = WorkflowCostMetric(session_id=session_id)
        db.add(row)
    row.planner_calls += 1
    row.tokens_used += max(0, tokens)
    row.planning_latency_ms += max(0, latency_ms)
    db.commit()


def get_analytics(db: Session, session_id: str) -> WorkflowAnalytics:
    session = db.get(WorkflowSession, session_id)
    if not session:
        raise LookupError("workflow session not found")
    budget = db.get(WorkflowBudgetRecord, session_id)
    cost = db.get(WorkflowCostMetric, session_id)
    events = db.query(WorkflowEvent).filter(WorkflowEvent.session_id == session_id).all()
    failures = db.query(FailureRecord).filter(FailureRecord.session_id == session_id).all()
    executed = [event for event in events if event.event_type == "executed"]
    successful = [event for event in executed if event.execution_result == "success"]
    success_rate = len(successful) / len(executed) if executed else 0.0
    recovered = sum(1 for failure in failures if failure.recovery_success)
    false_successes = sum(1 for failure in failures if failure.error_code == "FALSE_SUCCESS")
    false_success_rate = false_successes / len(successful) if successful else 0.0
    stability = max(0.0, 100.0 * (success_rate - false_success_rate) - len(failures) * 2)
    elapsed = max(0.0, (datetime.utcnow() - session.created_at).total_seconds())
    steps = budget.steps_used if budget else len(executed)
    planner_calls = cost.planner_calls if cost else 0
    tokens = cost.tokens_used if cost else 0
    return WorkflowAnalytics(
        session_id=session_id,
        status=session.status,
        budget_usage={
            "steps": {"used": budget.steps_used if budget else steps, "max": budget.max_steps if budget else 50},
            "retries": {"used": budget.retries_used if budget else recovered, "max": budget.max_retries if budget else 5},
            "tokens": {"used": budget.tokens_used if budget else tokens, "max": budget.max_tokens if budget else 50000},
            "duration_seconds": {"used": elapsed, "max": budget.max_duration_seconds if budget else 300},
        },
        token_usage=tokens,
        recovery_count=recovered,
        failure_types=dict(Counter(failure.error_code for failure in failures)),
        success_rate=success_rate,
        false_success_rate=false_success_rate,
        workflow_stability_score=stability,
        average_completion_time_seconds=elapsed / max(1, steps),
        cost_metrics=CostMetrics(
            planner_calls=planner_calls,
            vision_calls=cost.vision_calls if cost else 0,
            tokens_used=tokens,
            average_tokens_per_step=tokens / max(1, steps),
            average_planning_latency_ms=(cost.planning_latency_ms / planner_calls) if planner_calls else 0,
        ),
    )
