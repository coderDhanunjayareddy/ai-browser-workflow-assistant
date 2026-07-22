from __future__ import annotations

from app.cost_controller.budgets import CostUsage


class CostMeter:
    def __init__(self):
        self._usage: dict[str, CostUsage] = {}

    def record(
        self,
        run_id: str,
        *,
        tokens: int = 0,
        vision_calls: int = 0,
        provider_cost: float = 0.0,
        latency_ms: int = 0,
        workflow_duration_ms: int = 0,
    ) -> CostUsage:
        usage = self._usage.setdefault(run_id, CostUsage())
        usage.tokens += max(0, tokens)
        usage.vision_calls += max(0, vision_calls)
        usage.provider_cost += max(0.0, provider_cost)
        usage.latency_ms += max(0, latency_ms)
        usage.workflow_duration_ms += max(0, workflow_duration_ms)
        return usage

    def get(self, run_id: str) -> CostUsage:
        return self._usage.get(run_id, CostUsage())
