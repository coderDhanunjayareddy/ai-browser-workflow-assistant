from __future__ import annotations

from app.cost_controller.budgets import CostUsage


def usage_snapshot(run_id: str, usage: CostUsage) -> dict[str, int | float | str]:
    return {
        "run_id": run_id,
        "tokens": usage.tokens,
        "vision_calls": usage.vision_calls,
        "provider_cost": usage.provider_cost,
        "latency_ms": usage.latency_ms,
        "workflow_duration_ms": usage.workflow_duration_ms,
    }
