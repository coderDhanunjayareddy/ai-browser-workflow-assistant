"""
V9.0 Execution Planning Layer — ExecutionPlanPersistence (feature-flagged stub).

Follows the V4.6 / V7.0 / V8.x persistence pattern: a disabled-by-default flag.
Execution plans are in-memory by design in V9.0. This stub lets a later milestone
flip the flag and persist plans without changing call sites.

When execution_plan_persistence = False (default):
  - All plan state is in-memory via PlanRegistry.
  - save / load / delete are no-ops.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.execution_planning.models import ExecutionPlan

# Feature flag — disabled by default (V4.6 pattern).
execution_plan_persistence: bool = False


class ExecutionPlanPersistence:
    """No-op persistence facade. Active only if execution_plan_persistence is True."""

    def enabled(self) -> bool:
        return execution_plan_persistence

    def save(self, plan: "ExecutionPlan") -> None:
        if not execution_plan_persistence:
            return None
        return None

    def load_for_mission(self, mission_id: str) -> list:
        if not execution_plan_persistence:
            return []
        return []

    def delete_for_plan(self, plan_id: str) -> int:
        if not execution_plan_persistence:
            return 0
        return 0
