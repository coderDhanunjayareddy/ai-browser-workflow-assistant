"""
V8.9 Browser Runtime Layer — RuntimeContext builder (Mission Awareness).

The runtime always knows the current mission, task, approval state, and
authorization state. This module assembles a read-only RuntimeContext.

CRITICAL SAFETY CONTRACT:
  - Runtime READS authorization status; it NEVER evaluates or changes it.
  - `execution_ready` is exposed as UI metadata ONLY. It gates nothing.
  - All cross-module reads are non-blocking (try/except → graceful None).
"""
from __future__ import annotations

import time
from typing import Optional

from app.runtime import registry as session_reg
from app.runtime.models import RuntimeContext


class RuntimeContextBuilder:

    def build(self, runtime_id: str) -> RuntimeContext:
        now = time.time()
        session = session_reg.get(runtime_id)

        mission_id = session.active_mission_id if session else None
        task_id    = session.active_task_id    if session else None

        ctx = RuntimeContext(
            runtime_id        = runtime_id,
            active_mission_id = mission_id,
            active_task_id    = task_id,
            evaluated_at      = now,
        )

        if not mission_id:
            return ctx

        # Mission state (non-blocking)
        try:
            from app.mission import store as ms
            m = ms.get(mission_id)
            if m:
                ctx.mission_state = m.state.value
        except Exception:
            pass

        # Approval state (non-blocking, read-only)
        try:
            from app.approvals import queue as appr_queue
            ctx.approval_state = appr_queue.summary_for_mission(mission_id)
        except Exception:
            pass

        # Authorization state (non-blocking, read-only) — NEVER evaluates
        try:
            from app.authorization import registry as auth_reg
            auth_summary = auth_reg.summary_for_mission(mission_id)
            ctx.authorization_state = auth_summary
            # execution_ready is pure UI metadata: True iff there is at least one
            # active authorization that is currently executable for this mission.
            ctx.execution_ready = bool(auth_summary.get("active_authorizations", 0) > 0
                                       and len(auth_summary.get("executable_tasks", [])) > 0)
        except Exception:
            pass

        return ctx


# ── Module-level singleton ────────────────────────────────────────────────────

_builder = RuntimeContextBuilder()


def build(runtime_id: str) -> RuntimeContext:
    return _builder.build(runtime_id)
