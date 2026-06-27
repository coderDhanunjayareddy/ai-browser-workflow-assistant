"""
V8.0 Human Approval Center — ApprovalPersistence.

Feature-flagged stub following the V4.6 persistence pattern.
APPROVAL_PERSISTENCE = False  means all save/load calls are no-ops.

When persistence is needed in V9.x, flip the flag and implement DB writes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.approvals.models import ApprovalRequest

APPROVAL_PERSISTENCE: bool = False


class ApprovalPersistence:

    def save(self, item: "ApprovalRequest") -> None:
        if not APPROVAL_PERSISTENCE:
            return
        # TODO(V9.x): write to DB

    def load_for_mission(self, mission_id: str) -> list["ApprovalRequest"]:
        if not APPROVAL_PERSISTENCE:
            return []
        # TODO(V9.x): read from DB
        return []

    def delete_for_mission(self, mission_id: str) -> int:
        if not APPROVAL_PERSISTENCE:
            return 0
        # TODO(V9.x): delete from DB
        return 0
