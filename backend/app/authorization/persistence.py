"""
V8.8 Execution Authorization Framework — AuthorizationPersistence.

Feature-flagged stub. AUTHORIZATION_PERSISTENCE = False → all calls are no-ops.
V9.x will flip this flag and persist authorizations to a DB table for
durable execution gating.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.authorization.models import ExecutionAuthorization

AUTHORIZATION_PERSISTENCE: bool = False


class AuthorizationPersistence:

    def save(self, item: "ExecutionAuthorization") -> None:
        if not AUTHORIZATION_PERSISTENCE:
            return
        # TODO(V9.x): persist to DB

    def load_for_mission(self, mission_id: str) -> list["ExecutionAuthorization"]:
        if not AUTHORIZATION_PERSISTENCE:
            return []
        # TODO(V9.x): load from DB
        return []

    def delete_for_mission(self, mission_id: str) -> int:
        if not AUTHORIZATION_PERSISTENCE:
            return 0
        # TODO(V9.x): delete from DB
        return 0
