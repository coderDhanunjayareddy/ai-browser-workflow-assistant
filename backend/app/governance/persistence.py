"""
V8.5 Governance Layer — GovernancePersistence.

Feature-flagged stub following the V4.6 persistence pattern.
GOVERNANCE_PERSISTENCE = False → all save/load calls are no-ops.

V9.x will flip this flag and write contracts to a DB table so
the execution gateway can query approved contracts durably.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.governance.models import GovernanceContract

GOVERNANCE_PERSISTENCE: bool = False


class GovernancePersistence:

    def save(self, contract: "GovernanceContract") -> None:
        if not GOVERNANCE_PERSISTENCE:
            return
        # TODO(V9.x): write to DB

    def load_for_mission(self, mission_id: str) -> list["GovernanceContract"]:
        if not GOVERNANCE_PERSISTENCE:
            return []
        # TODO(V9.x): read from DB
        return []

    def delete_for_mission(self, mission_id: str) -> int:
        if not GOVERNANCE_PERSISTENCE:
            return 0
        # TODO(V9.x): delete from DB
        return 0
