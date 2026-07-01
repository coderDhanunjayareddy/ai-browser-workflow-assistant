"""
M0 — Metrics collection + aggregation.

Turns a list of M0TaskResult into the full metrics block: primary metrics (completion,
step-success, human-intervention, recovery, validation), secondary diagnostics (timings,
tokens, cost), Wilson 95% confidence intervals, and the failure / locator distributions.

Reuses app.certification.reliability for the workflow-success rollup (records each task as
a WorkflowOutcome) so M0 does not duplicate that register.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from benchmark.m0_models import (
    M0TaskResult, TaskStatus, FailureCategory, BLOCKED_CATEGORIES,
)

# Gemini flash-class pricing (USD per 1M tokens). Override via set_token_rates().
_RATE_PROMPT_PER_M = 0.075
_RATE_COMPLETION_PER_M = 0.30


def set_token_rates(prompt_per_m: float, completion_per_m: float) -> None:
    global _RATE_PROMPT_PER_M, _RATE_COMPLETION_PER_M
    _RATE_PROMPT_PER_M = prompt_per_m
    _RATE_COMPLETION_PER_M = completion_per_m


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens / 1_000_000 * _RATE_PROMPT_PER_M
            + completion_tokens / 1_000_000 * _RATE_COMPLETION_PER_M)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score 95% CI for a proportion. Returns (low, high) in [0,1]."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - margin) / denom), min(1.0, (centre + margin) / denom))


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def _tier_block(results: list[M0TaskResult]) -> dict[str, Any]:
    counted = [r for r in results if r.counts_toward_completion]
    completed = sum(1 for r in counted if r.is_completed)
    n = len(counted)
    lo, hi = wilson_interval(completed, n)
    return {
        "attempted": n,
        "completed": completed,
        "completion_rate": _rate(completed, n),
        "completion_rate_ci_95": [round(lo, 4), round(hi, 4)],
        "blocked": sum(1 for r in results if r.is_blocked),
        "skipped": sum(1 for r in results if r.status == TaskStatus.skipped),
    }


def feed_reliability(results: list[M0TaskResult]) -> None:
    """Record each counted task into the shared certification reliability register."""
    try:
        from app.certification import reliability
        from app.certification.models import WorkflowOutcome
    except Exception:
        return
    for r in results:
        if not r.counts_toward_completion:
            continue
        reliability.record_workflow(WorkflowOutcome(
            scenario_id=r.task_id, category=r.category, website=r.website,
            passed=r.is_completed, duration_ms=r.duration_ms, real_browser=True))


def aggregate(results: list[M0TaskResult], *, executor_mode: str) -> dict[str, Any]:
    counted = [r for r in results if r.counts_toward_completion]
    n = len(counted)
    completed = sum(1 for r in counted if r.is_completed)
    lo, hi = wilson_interval(completed, n)

    # primary aggregate counters
    total_steps = sum(r.steps_taken for r in results)
    step_success = sum(r.steps_successful for r in results)
    human_steps = sum(r.human_interventions for r in results)
    recoveries = sum(r.recoveries_attempted for r in results)
    recoveries_ok = sum(r.recoveries_successful for r in results)
    val_attempted = sum(r.validations_attempted for r in results)
    val_passed = sum(r.validations_passed for r in results)

    # cost / tokens
    prompt_tokens = sum(s.prompt_tokens for r in results for s in r.steps)
    completion_tokens = sum(s.completion_tokens for r in results for s in r.steps)
    cost = estimate_cost_usd(prompt_tokens, completion_tokens)

    summary = {
        "tasks_attempted": len(results),
        "tasks_completed": sum(1 for r in results if r.status == TaskStatus.completed),
        "tasks_failed": sum(1 for r in results if r.status == TaskStatus.failed),
        "tasks_timeout": sum(1 for r in results if r.status == TaskStatus.timeout),
        "tasks_stuck": sum(1 for r in results if r.status == TaskStatus.stuck),
        "tasks_blocked": sum(1 for r in results if r.status == TaskStatus.blocked),
        "tasks_skipped": sum(1 for r in results if r.status == TaskStatus.skipped),
        "tasks_error": sum(1 for r in results if r.status == TaskStatus.error),
        "tasks_counted": n,
        # PRIMARY METRICS
        "completion_rate": _rate(completed, n),
        "completion_rate_ci_95": [round(lo, 4), round(hi, 4)],
        "step_success_rate": _rate(step_success, total_steps),
        "human_intervention_rate": _rate(human_steps, total_steps),
        "recovery_success_rate": _rate(recoveries_ok, recoveries),
        "validation_pass_rate": _rate(val_passed, val_attempted),
        # cost
        "estimated_cost_usd": round(cost, 4),
        "total_prompt_tokens": prompt_tokens,
        "total_completion_tokens": completion_tokens,
    }

    # secondary diagnostics
    durations = [r.duration_ms for r in results if r.steps_taken > 0]
    secondary = {
        "avg_observe_time_ms": _avg(r.observe_time_ms for r in results),
        "avg_analyze_time_ms": _avg(r.analyze_time_ms for r in results),
        "avg_execute_time_ms": _avg(r.execute_time_ms for r in results),
        "avg_validate_time_ms": _avg(r.validate_time_ms for r in results),
        "p95_task_duration_ms": _percentile(durations, 95),
        "avg_steps_per_task": _avg(float(r.steps_taken) for r in results),
        "avg_ai_calls_per_completed": _avg(float(r.ai_calls) for r in results if r.is_completed),
        "avg_tokens_per_task": _avg(float(r.total_tokens) for r in results),
        "estimated_cost_per_task_usd": round(cost / len(results), 5) if results else 0.0,
    }

    # breakdowns
    by_difficulty = {tier: _tier_block([r for r in results if r.difficulty == tier])
                     for tier in ("simple", "medium", "complex")}
    by_category = _group_block(results, key=lambda r: r.category)
    by_site = _group_block(results, key=lambda r: r.website)

    # failure + locator distributions
    failure_distribution: dict[str, int] = {}
    for r in results:
        if r.failure_category:
            failure_distribution[r.failure_category] = failure_distribution.get(r.failure_category, 0) + 1
    locator_strategies: dict[str, int] = {}
    for r in results:
        for strat, cnt in r.locator_strategy_counts.items():
            locator_strategies[strat] = locator_strategies.get(strat, 0) + cnt

    # blocked rate (informational)
    blocked = sum(1 for r in results if r.is_blocked)
    summary["captcha_blocked_rate"] = _rate(
        sum(1 for r in results if r.failure_category == FailureCategory.blocked_captcha.value),
        len(results))

    return {
        "executor_mode": executor_mode,
        "summary": summary,
        "secondary": secondary,
        "by_difficulty": by_difficulty,
        "by_category": by_category,
        "by_site": by_site,
        "failure_distribution": failure_distribution,
        "locator_strategies": locator_strategies,
        "blocked_total": blocked,
    }


def _group_block(results, key) -> dict[str, Any]:
    groups: dict[str, list[M0TaskResult]] = {}
    for r in results:
        groups.setdefault(key(r), []).append(r)
    out = {}
    for name, items in sorted(groups.items()):
        counted = [r for r in items if r.counts_toward_completion]
        completed = sum(1 for r in counted if r.is_completed)
        out[name] = {
            "attempted": len(counted),
            "completed": completed,
            "completion_rate": _rate(completed, len(counted)),
            "blocked": sum(1 for r in items if r.is_blocked),
        }
    return out


def _avg(values) -> float:
    vals = [v for v in values]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 2)
    k = (pct / 100.0) * (len(s) - 1)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 2)


def executor_gap(playwright_agg: dict, synthetic_agg: dict) -> dict[str, Any]:
    """Per-tier (playwright - synthetic) completion gap. Quantifies the M1 opportunity."""
    out = {}
    for tier in ("simple", "medium", "complex", "overall"):
        if tier == "overall":
            pr = playwright_agg["summary"]["completion_rate"]
            sr = synthetic_agg["summary"]["completion_rate"]
        else:
            pr = playwright_agg["by_difficulty"][tier]["completion_rate"]
            sr = synthetic_agg["by_difficulty"][tier]["completion_rate"]
        out[tier] = {"playwright": pr, "synthetic": sr, "gap": round(pr - sr, 4)}
    return out
