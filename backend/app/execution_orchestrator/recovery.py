from __future__ import annotations

from app.execution_orchestrator.models import ExecutionBudgets, PhaseState, RecoveryRoute


def route_recovery(active_phase: PhaseState, budgets: ExecutionBudgets, rejected: bool = False) -> RecoveryRoute:
    if budgets.exhausted:
        return RecoveryRoute("report_partial", active_phase.name, f"budget exhausted: {', '.join(budgets.exhausted)}")
    if rejected:
        return RecoveryRoute("retry_phase", active_phase.name, "planner action violated active phase constraints")
    if active_phase.retry_count >= 3:
        return RecoveryRoute("blocked", active_phase.name, "phase retry budget exceeded")
    return RecoveryRoute("none", active_phase.name, "phase can continue")
