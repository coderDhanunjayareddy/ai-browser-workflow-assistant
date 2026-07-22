from __future__ import annotations

from app.cost_controller.budgets import CostBudget, CostDecision, CostUsage


def evaluate_budget(run_id: str, budget: CostBudget, usage: CostUsage) -> CostDecision:
    if budget.max_tokens and usage.tokens >= budget.max_tokens:
        return CostDecision(run_id=run_id, status="exceeded", reason="token_budget_exceeded")
    if budget.max_latency_ms and usage.latency_ms >= budget.max_latency_ms:
        return CostDecision(run_id=run_id, status="exceeded", reason="latency_budget_exceeded")
    near_token_limit = budget.max_tokens and usage.tokens >= int(budget.max_tokens * 0.8)
    near_latency_limit = budget.max_latency_ms and usage.latency_ms >= int(budget.max_latency_ms * 0.8)
    if near_token_limit or near_latency_limit:
        return CostDecision(
            run_id=run_id,
            status="near_limit",
            reason="budget_near_limit",
            planner_guidance="Prefer concise evidence gathering and avoid unnecessary provider calls.",
        )
    return CostDecision(run_id=run_id, status="within_budget", reason="within_budget")
