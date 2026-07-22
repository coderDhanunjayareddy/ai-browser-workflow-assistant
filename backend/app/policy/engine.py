from __future__ import annotations

import time
from typing import Any

from app.policy.constraints import evaluate_constraints
from app.policy.models import ExecutionConstraints, GovernanceObject
from app.policy.rules import classify_action_risk
from app.policy.scheduler import GovernanceScheduler
from app.policy.telemetry import record_governance_metrics
from app.schemas.response import SuggestedAction


class GovernanceDecisionEngine:
    """Deterministic V3.5 policy and governance pipeline.

    The engine evaluates execution requests. It never executes actions, changes
    planner output, or owns mission state.
    """

    def __init__(
        self,
        *,
        constraints: ExecutionConstraints | None = None,
        scheduler: GovernanceScheduler | None = None,
    ):
        self.constraints = constraints or ExecutionConstraints()
        self.scheduler = scheduler or GovernanceScheduler()

    def evaluate_action(
        self,
        *,
        run_id: str,
        mission_id: str,
        step_id: str,
        action: SuggestedAction,
        runtime: dict[str, Any] | None = None,
    ) -> tuple[GovernanceObject, int]:
        started = time.perf_counter()
        policy_started = time.perf_counter()
        risk_level, approval_hooks, reasons = classify_action_risk(action)
        policy_ms = int((time.perf_counter() - policy_started) * 1000)

        constraint_started = time.perf_counter()
        violations = evaluate_constraints(
            action=action,
            constraints=self.constraints,
            runtime=runtime,
        )
        constraints_ms = int((time.perf_counter() - constraint_started) * 1000)

        decision = "allow"
        approval_required = False
        requires_handoff = False
        if violations:
            decision = "defer" if "rate_limit_exceeded" in violations else "block"
        elif risk_level == "critical":
            decision = "handoff_required"
            approval_required = True
            requires_handoff = True
        elif risk_level == "danger":
            decision = "allow_with_confirmation"
            approval_required = True
        elif risk_level == "caution":
            decision = "warn"

        reason = ";".join([*reasons, *violations]) or "policy_allow"
        governance = GovernanceObject(
            run_id=run_id,
            mission_id=mission_id,
            step_id=step_id,
            policy_decision=decision,  # type: ignore[arg-type]
            execution_constraints=self.constraints,
            approval_required=approval_required,
            requires_handoff=requires_handoff,
            decision_reason=reason,
            confidence=0.95 if not violations else 0.9,
            risk_level=risk_level,  # type: ignore[arg-type]
            constraints_violated=violations,
            approval_hooks=approval_hooks,
            replay_metadata={
                "pipeline": "action_governance",
                "policy_ms": policy_ms,
                "constraints_ms": constraints_ms,
                "action_type": action.action_type,
                "action_id": action.action_id,
            },
        )
        item = self.scheduler.schedule(run_id=run_id, governance=governance)
        governance.scheduler_item_id = item.id
        governance.scheduler_status = item.status
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_governance_metrics(run_id, governance, latency_ms=latency_ms)
        return governance, latency_ms
