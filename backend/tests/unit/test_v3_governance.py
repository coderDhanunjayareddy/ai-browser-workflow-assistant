from __future__ import annotations

from datetime import datetime, timezone

from app.feature_flags import is_shadow_or_active
from app.observability.metrics import default_metric_sink
from app.policy import ExecutionConstraints, GovernanceDecisionEngine, replay_governance
from app.policy.scheduler import GovernanceScheduler
from app.policy.telemetry import record_governance_metrics
from app.scheduler.queue import InMemorySchedulerQueue
from app.schemas.response import SuggestedAction


def action(
    *,
    action_id: str = "act-1",
    action_type: str = "click",
    description: str = "Click Continue",
    reasoning: str = "Continue the workflow",
    selector: str = "#continue",
    value: str | None = None,
    safety_level: str = "safe",
) -> SuggestedAction:
    return SuggestedAction(
        action_id=action_id,
        action_type=action_type,  # type: ignore[arg-type]
        target_selector=selector,
        value=value,
        description=description,
        reasoning=reasoning,
        confidence=0.8,
        safety_level=safety_level,  # type: ignore[arg-type]
    )


def test_governance_allows_safe_execution_request():
    governance, latency_ms = GovernanceDecisionEngine().evaluate_action(
        run_id="run-1",
        mission_id="run-1",
        step_id="act-1",
        action=action(),
    )

    assert governance.schema_version == "governance.v1"
    assert governance.policy_decision == "allow"
    assert governance.approval_required is False
    assert governance.requires_handoff is False
    assert governance.risk_level == "safe"
    assert governance.scheduler_item_id
    assert latency_ms < 50


def test_governance_requires_approval_for_irreversible_action():
    governance, _ = GovernanceDecisionEngine().evaluate_action(
        run_id="run-1",
        mission_id="run-1",
        step_id="act-pay",
        action=action(
            action_id="act-pay",
            description="Click Pay Invoice",
            reasoning="Submit payment for the invoice",
            safety_level="caution",
        ),
    )

    assert governance.policy_decision == "allow_with_confirmation"
    assert governance.approval_required is True
    assert "irreversible_external_action" in governance.approval_hooks


def test_governance_requires_handoff_for_sensitive_input():
    governance, _ = GovernanceDecisionEngine().evaluate_action(
        run_id="run-1",
        mission_id="run-1",
        step_id="act-password",
        action=action(
            action_id="act-password",
            action_type="fill",
            description="Fill password",
            reasoning="Enter account password",
            value="secret",
            selector="#password",
        ),
    )

    assert governance.policy_decision == "handoff_required"
    assert governance.approval_required is True
    assert governance.requires_handoff is True
    assert "sensitive_input" in governance.approval_hooks


def test_governance_blocks_constraint_violations():
    governance, _ = GovernanceDecisionEngine(
        constraints=ExecutionConstraints(max_retries=1)
    ).evaluate_action(
        run_id="run-1",
        mission_id="run-1",
        step_id="act-retry",
        action=action(),
        runtime={"retry_count": 2},
    )

    assert governance.policy_decision == "block"
    assert governance.constraints_violated == ["max_retries_exceeded"]


def test_governance_defers_rate_limited_action():
    governance, _ = GovernanceDecisionEngine(
        constraints=ExecutionConstraints(rate_limit_per_minute=1)
    ).evaluate_action(
        run_id="run-1",
        mission_id="run-1",
        step_id="act-rate",
        action=action(),
        runtime={"actions_last_minute": 2},
    )

    assert governance.policy_decision == "defer"
    assert governance.scheduler_status == "delayed"
    assert "rate_limit_exceeded" in governance.constraints_violated


def test_governance_scheduler_queue_activates_without_routing_workflow(monkeypatch):
    from app.core.config import settings

    queue = InMemorySchedulerQueue()
    scheduler = GovernanceScheduler(queue)
    governance, _ = GovernanceDecisionEngine(scheduler=scheduler).evaluate_action(
        run_id="run-1",
        mission_id="run-1",
        step_id="act-1",
        action=action(),
    )

    assert queue.get(governance.scheduler_item_id or "") is not None
    monkeypatch.setattr(settings, "v3_scheduler", "off")
    assert queue.due_items(datetime.now(timezone.utc)) == []
    monkeypatch.setattr(settings, "v3_scheduler", "active")
    assert len(queue.due_items(datetime.now(timezone.utc))) == 1


def test_governance_replay_is_identical_for_identical_input():
    governance, _ = GovernanceDecisionEngine().evaluate_action(
        run_id="run-1",
        mission_id="run-1",
        step_id="act-1",
        action=action(),
    )

    replayed, replay_ms = replay_governance(governance)

    assert replayed.to_stable_json() == governance.to_stable_json()
    assert replay_ms < 100


def test_governance_feature_flag_default_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_governance", "shadow")
    assert is_shadow_or_active("V3_GOVERNANCE") is True
    assert is_shadow_or_active("V3_POLICY_ENGINE") is True

    monkeypatch.setattr(settings, "v3_governance", "off")
    assert is_shadow_or_active("V3_GOVERNANCE") is False


def test_governance_telemetry_records_metrics():
    governance, latency_ms = GovernanceDecisionEngine().evaluate_action(
        run_id="run-telemetry",
        mission_id="run-telemetry",
        step_id="act-1",
        action=action(),
    )

    before = _metric_counts()
    record_governance_metrics("run-telemetry", governance, latency_ms=latency_ms)
    after = _metric_counts()

    for name in {
        "v3.governance.latency_ms",
        "v3.governance.decision",
        "v3.governance.confidence",
        "v3.scheduler.activity",
    }:
        assert after.get(name, 0) >= before.get(name, 0)


def _metric_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for point in default_metric_sink.snapshot():
        counts[point.name] = counts.get(point.name, 0) + 1
    return counts
