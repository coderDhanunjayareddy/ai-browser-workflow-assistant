from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.policy.models import GovernanceObject
from app.scheduler import InMemorySchedulerQueue, ScheduledWorkItem


class GovernanceScheduler:
    def __init__(self, queue: InMemorySchedulerQueue | None = None):
        self.queue = queue or InMemorySchedulerQueue()

    def schedule(self, *, run_id: str, governance: GovernanceObject) -> ScheduledWorkItem:
        delay_seconds = 1 if governance.policy_decision == "defer" else 0
        item = ScheduledWorkItem(
            run_id=run_id,
            kind="governance.execution_request",
            status="delayed" if delay_seconds else "pending",
            earliest_start_at=datetime.now(timezone.utc) + timedelta(seconds=delay_seconds),
            max_attempts=governance.execution_constraints.max_retries,
            payload={
                "governance_id": governance.governance_id,
                "policy_decision": governance.policy_decision,
                "approval_required": governance.approval_required,
                "requires_handoff": governance.requires_handoff,
            },
        )
        return self.queue.enqueue(item)
