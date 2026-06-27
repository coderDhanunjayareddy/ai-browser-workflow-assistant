"""
Phase B — Execution Gateway V1 — Rollback Engine.

SIMULATES rollback using the rollback metadata already attached to each step
(from the V9.0 RollbackPlanner). It NEVER performs a browser action — it produces a
rollback report describing what WOULD be undone, in reverse order.
"""
from __future__ import annotations

from typing import Any

from app.execution_gateway.models import StepExecution


class RollbackEngine:

    def simulate(self, completed_steps: list[StepExecution]) -> list[dict[str, Any]]:
        """
        Build a reverse-order rollback report for the steps that already ran.
        Marks each step's rollback as performed (simulated) and returns descriptors.
        """
        report: list[dict[str, Any]] = []
        for step in sorted(completed_steps, key=lambda s: s.order, reverse=True):
            step.rollback_performed = True
            report.append({
                "step_id":       step.step_id,
                "order":         step.order,
                "action_type":   step.action_type,
                "command_type":  step.command_type,
                "simulated":     True,
                "note":          "rollback simulated (no browser action performed)",
            })
        return report

    def rollback_count(self, report: list[dict]) -> int:
        return len(report)


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = RollbackEngine()


def simulate(completed_steps: list[StepExecution]) -> list[dict]:
    return _engine.simulate(completed_steps)
