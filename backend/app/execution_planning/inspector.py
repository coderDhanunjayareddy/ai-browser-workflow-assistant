"""
V9.0 Execution Planning Layer — PlanInspector.

Single read-only debugging surface for one ExecutionPlan.
Aggregates: the plan + steps, rollback plan, live validation, authorization
linkage (read-only), mission context, timeline summary, and analytics.

NO execution. NO mutation. NO LLM.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.execution_planning import analytics as anal
from app.execution_planning import registry as plan_reg
from app.execution_planning import rollback as rollback_planner
from app.execution_planning import timeline as tl
from app.execution_planning import validator as plan_validator


class PlanInspector:

    def inspect(self, plan_id: str) -> Optional[dict[str, Any]]:
        t0 = time.perf_counter()
        plan = plan_reg.get(plan_id)
        if plan is None:
            return None

        # Rollback plan (metadata only)
        rollback = rollback_planner.plan_rollback(plan.steps)

        # Live validation snapshot (read-only; does not record analytics)
        validation = plan_validator.validate(plan).to_dict()

        # Authorization linkage (read-only)
        authorization: Optional[dict] = None
        try:
            from app.authorization import registry as auth_reg
            auth = auth_reg.get(plan.authorization_id)
            if auth is not None:
                authorization = {
                    "authorization_id": auth.authorization_id,
                    "status":           auth.status.value,
                    "is_executable":    auth.is_executable,
                    "risk_level":       auth.risk_level,
                }
        except Exception:
            pass

        # Mission context (read-only)
        mission_context: Optional[dict] = None
        try:
            if plan.mission_id:
                from app.mission import store as ms
                m = ms.get(plan.mission_id)
                if m is not None:
                    mission_context = {
                        "mission_id": m.mission_id,
                        "state":      m.state.value,
                        "task_count": m.task_count,
                    }
        except Exception:
            pass

        # Timeline summary (read-only)
        timeline_summary: Optional[dict] = None
        try:
            if plan.mission_id:
                timeline_summary = tl.summary(plan.mission_id)
        except Exception:
            pass

        latency_ms = round((time.perf_counter() - t0) * 1000, 3)

        return {
            "plan_id":           plan_id,
            "plan":              plan.to_dict(include_steps=True),
            "step_count":        len(plan.steps),
            "mutating_steps":    plan.mutating_step_count,
            "rollback":          rollback,
            "validation":        validation,
            "authorization":     authorization,
            "mission_context":   mission_context,
            "timeline_summary":  timeline_summary,
            "analytics":         anal.get_analytics(),
            "registry_stats":    plan_reg.stats(),
            "latency_ms":        latency_ms,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_inspector = PlanInspector()


def inspect(plan_id: str) -> Optional[dict]:
    return _inspector.inspect(plan_id)
