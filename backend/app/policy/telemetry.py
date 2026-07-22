from __future__ import annotations

from app.observability.metrics import default_metric_sink
from app.policy.models import GovernanceObject


def record_governance_metrics(
    run_id: str,
    governance: GovernanceObject,
    *,
    latency_ms: int,
) -> None:
    tags = {
        "decision": governance.policy_decision,
        "risk_level": governance.risk_level,
        "approval_required": str(governance.approval_required).lower(),
        "requires_handoff": str(governance.requires_handoff).lower(),
    }
    default_metric_sink.record("v3.governance.latency_ms", latency_ms, run_id=run_id, tags=tags)
    default_metric_sink.record("v3.governance.decision", 1, run_id=run_id, tags=tags)
    default_metric_sink.record(
        "v3.governance.confidence",
        governance.confidence,
        run_id=run_id,
        tags=tags,
    )
    if governance.policy_decision == "block":
        default_metric_sink.record("v3.governance.denied", 1, run_id=run_id, tags=tags)
    if governance.approval_required:
        default_metric_sink.record("v3.governance.approval_required", 1, run_id=run_id, tags=tags)
    if governance.constraints_violated:
        default_metric_sink.record(
            "v3.governance.constraint_violation",
            len(governance.constraints_violated),
            run_id=run_id,
            tags=tags,
        )
    if governance.scheduler_item_id:
        default_metric_sink.record("v3.scheduler.activity", 1, run_id=run_id, tags=tags)
