"""
Phase B — Execution Gateway V1 — GatewayInspector.

Single read-only debugging surface for one execution run.
Shows: current step, completed / remaining, execution history, retry history,
rollback history, validation results, adapter used, audit trail, analytics.

NO execution. NO mutation. NO browser code.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.execution_gateway import analytics as gw_analytics
from app.execution_gateway import audit as audit_trail
from app.execution_gateway import registry as exec_registry


class GatewayInspector:

    def inspect(self, execution_id: str) -> Optional[dict[str, Any]]:
        t0 = time.perf_counter()
        record = exec_registry.get(execution_id)
        if record is None:
            return None

        steps = record.step_executions
        completed = [s for s in steps if s.outcome.value == "SUCCESS"]
        failed    = [s for s in steps if s.outcome.value in ("FAILED", "VALIDATION_FAILED")]

        current_step = None
        if not record.is_terminal and record.current_step_index < record.total_steps:
            current_step = {
                "index": record.current_step_index,
                "remaining": record.remaining_steps,
            }

        retry_history = [
            {"step_id": s.step_id, "order": s.order, "attempts": s.attempts,
             "retries": max(0, s.attempts - 1), "outcome": s.outcome.value}
            for s in steps if s.attempts > 1
        ]

        validation_results = [
            {"step_id": s.step_id, "order": s.order, "validation_passed": s.validation_passed,
             "outcome": s.outcome.value}
            for s in steps
        ]

        audit_entries = [e.to_dict() for e in audit_trail.entries_for_execution(execution_id, limit=100)]

        # Mission context (read-only, non-blocking)
        mission_context: Optional[dict] = None
        try:
            if record.mission_id:
                from app.mission import store as ms
                m = ms.get(record.mission_id)
                if m is not None:
                    mission_context = {"mission_id": m.mission_id, "state": m.state.value}
        except Exception:
            pass

        latency_ms = round((time.perf_counter() - t0) * 1000, 3)

        return {
            "execution_id":       execution_id,
            "state":              record.state.value,
            "adapter_used":       record.adapter_name,
            "plan_id":            record.plan_id,
            "authorization_id":   record.authorization_id,
            "current_step":       current_step,
            "total_steps":        record.total_steps,
            "completed_steps":    len(completed),
            "failed_steps":       len(failed),
            "remaining_steps":    record.remaining_steps,
            "execution_history":  [s.to_dict() for s in steps],
            "retry_history":      retry_history,
            "rollback_history":   record.rollback_history,
            "validation_results": validation_results,
            "audit_trail":        audit_entries,
            "preflight":          record.preflight,
            "mission_context":    mission_context,
            "total_retries":      record.total_retries,
            "total_duration_ms":  record.total_duration_ms,
            "analytics":          gw_analytics.get_analytics(),
            "registry_stats":     exec_registry.stats(),
            "audit_stats":        audit_trail.stats(),
            "latency_ms":         latency_ms,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_inspector = GatewayInspector()


def inspect(execution_id: str) -> Optional[dict]:
    return _inspector.inspect(execution_id)
