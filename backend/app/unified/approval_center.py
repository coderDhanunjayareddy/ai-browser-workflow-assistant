"""
V4.5 Unified Task Graph — ApprovalCenter.

Task-scoped approval records replace anonymous WorkflowEvent approvals.
Every approval request is now attached to a UnifiedTask so the full
approval lifecycle can be queried by task_id.

Safety guarantee: The ApprovalCenter is a record-keeping layer ONLY.
It does NOT execute actions, trigger workflows, or bypass any safety checks.
Execution only proceeds when the user explicitly approves via the UI.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.unified.models import (
    ApprovalRecord, ApprovalStatus, UnifiedTask,
)
from app.unified import store as task_store
from app.unified import task_timeline


class ApprovalCenter:
    """Create and resolve task-scoped approval records."""

    # ── Create ────────────────────────────────────────────────────────────────

    def request(
        self,
        task: UnifiedTask,
        action: str,
        risk_level: str,
    ) -> ApprovalRecord:
        """Create a PENDING approval record for a task."""
        record = ApprovalRecord(
            approval_id=str(uuid.uuid4())[:8],
            task_id=task.task_id,
            action=action,
            risk_level=risk_level,
            status=ApprovalStatus.pending,
        )
        task.approvals.append(record)
        task.touch()
        task_store.put(task)
        task_timeline.record_approval_requested(task, action, risk_level)
        # V4.6: persist
        try:
            from app.unified import approval_persistence
            approval_persistence.save(record)
        except Exception:
            pass
        return record

    # ── Resolve ───────────────────────────────────────────────────────────────

    def approve(
        self,
        task: UnifiedTask,
        approval_id: str,
        note: str = "",
    ) -> Optional[ApprovalRecord]:
        """Mark an approval as APPROVED."""
        record = self._find(task, approval_id)
        if record is None or record.status != ApprovalStatus.pending:
            return None
        record.status = ApprovalStatus.approved
        record.resolved_at = datetime.utcnow()
        record.resolution_note = note
        task.touch()
        task_store.put(task)
        task_timeline.record_approval_granted(task, record.action)
        try:
            from app.unified import approval_persistence
            approval_persistence.save(record)
        except Exception:
            pass
        return record

    def deny(
        self,
        task: UnifiedTask,
        approval_id: str,
        reason: str = "",
    ) -> Optional[ApprovalRecord]:
        """Mark an approval as DENIED."""
        record = self._find(task, approval_id)
        if record is None or record.status != ApprovalStatus.pending:
            return None
        record.status = ApprovalStatus.denied
        record.resolved_at = datetime.utcnow()
        record.resolution_note = reason
        task.touch()
        task_store.put(task)
        task_timeline.record_approval_denied(task, record.action, reason)
        try:
            from app.unified import approval_persistence
            approval_persistence.save(record)
        except Exception:
            pass
        return record

    def expire_pending(self, task: UnifiedTask) -> int:
        """Mark all PENDING approvals as EXPIRED. Returns count expired."""
        expired = 0
        for rec in task.approvals:
            if rec.status == ApprovalStatus.pending:
                rec.status = ApprovalStatus.expired
                rec.resolved_at = datetime.utcnow()
                expired += 1
        if expired:
            task.touch()
            task_store.put(task)
        return expired

    # ── Query ─────────────────────────────────────────────────────────────────

    def pending(self, task: UnifiedTask) -> list[ApprovalRecord]:
        return [a for a in task.approvals if a.status == ApprovalStatus.pending]

    def history(self, task: UnifiedTask) -> list[ApprovalRecord]:
        return list(task.approvals)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _find(self, task: UnifiedTask, approval_id: str) -> Optional[ApprovalRecord]:
        for rec in task.approvals:
            if rec.approval_id == approval_id:
                return rec
        return None


# Module-level singleton
_center = ApprovalCenter()


def request(task: UnifiedTask, action: str, risk_level: str) -> ApprovalRecord:
    return _center.request(task, action, risk_level)


def approve(task: UnifiedTask, approval_id: str, note: str = "") -> Optional[ApprovalRecord]:
    return _center.approve(task, approval_id, note)


def deny(task: UnifiedTask, approval_id: str, reason: str = "") -> Optional[ApprovalRecord]:
    return _center.deny(task, approval_id, reason)


def expire_pending(task: UnifiedTask) -> int:
    return _center.expire_pending(task)


def pending(task: UnifiedTask) -> list[ApprovalRecord]:
    return _center.pending(task)


def history(task: UnifiedTask) -> list[ApprovalRecord]:
    return _center.history(task)
