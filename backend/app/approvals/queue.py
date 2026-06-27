"""
V8.0 Human Approval Center — ApprovalQueue.

Filtered views over the ApprovalRegistry.
All views are read-only — no mutations here.
"""
from __future__ import annotations

from app.approvals import registry as reg
from app.approvals.models import ApprovalRequest, ApprovalStatus, ApprovalRiskLevel


def all_pending(limit: int = 100) -> list[ApprovalRequest]:
    """All PENDING approvals, highest risk first."""
    return reg.list_pending(limit=limit)


def critical(limit: int = 50) -> list[ApprovalRequest]:
    """PENDING approvals with HIGH or CRITICAL risk level."""
    return reg.list_critical(limit=limit)


def for_mission(mission_id: str, limit: int = 100) -> list[ApprovalRequest]:
    """All approvals (any status) for a specific mission."""
    return reg.list_for_mission(mission_id, limit=limit)


def pending_for_mission(mission_id: str, limit: int = 100) -> list[ApprovalRequest]:
    """PENDING approvals for a specific mission."""
    return [r for r in reg.list_for_mission(mission_id, limit=1000)
            if r.status == ApprovalStatus.pending][:limit]


def for_task(task_id: str, limit: int = 100) -> list[ApprovalRequest]:
    """All approvals for a specific task."""
    return reg.list_for_task(task_id, limit=limit)


def summary_for_mission(mission_id: str) -> dict:
    """Approval summary counts for a mission — used by Mission Inspector."""
    items = reg.list_for_mission(mission_id, limit=1000)
    pending  = sum(1 for r in items if r.status == ApprovalStatus.pending)
    approved = sum(1 for r in items if r.status == ApprovalStatus.approved)
    rejected = sum(1 for r in items if r.status == ApprovalStatus.rejected)
    critical_count = sum(1 for r in items
                         if r.status == ApprovalStatus.pending
                         and r.risk_level in (ApprovalRiskLevel.critical, ApprovalRiskLevel.high))
    return {
        "total":    len(items),
        "pending":  pending,
        "approved": approved,
        "rejected": rejected,
        "critical": critical_count,
    }
