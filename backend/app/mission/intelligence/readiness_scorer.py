"""
V5.5 Mission Intelligence — MissionReadinessScorer.

Computes a readiness score (0.0–1.0) from mission context.

Score bands (approximate):
  0.00–0.15  No tasks or all failed
  0.15–0.35  Tasks exist, some research
  0.35–0.60  Research complete, comparison in progress
  0.60–0.80  Multiple tasks complete, research + data available
  0.80–0.95  All tasks complete, execution plan present
  0.95–1.00  Fully ready (no blockers, plan ready, all info present)

Inputs come from MissionContext (single call to context_registry.get_context).
No DB. No LLM. Pure deterministic math.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.mission.context_registry import MissionContext


@dataclass
class ReadinessDetail:
    """Intermediate breakdown used for reasoning and testing."""
    total_tasks:        int
    completed_tasks:    int
    failed_tasks:       int
    has_research:       bool
    has_execution_plan: bool
    has_decisions:      bool
    blocker_count:      int
    missing_info_count: int
    completion_rate:    float
    score:              float


def compute(
    total_tasks:        int,
    completed_tasks:    int,
    failed_tasks:       int,
    has_research:       bool,
    has_execution_plan: bool,
    has_decisions:      bool,
    blocker_count:      int,
    missing_info_count: int,
) -> float:
    """
    Pure function: compute readiness score from counters.
    Exposed for unit testing without needing a full MissionContext.
    """
    if total_tasks == 0:
        return 0.05 if has_research else 0.0

    completion_rate = completed_tasks / total_tasks

    # Base: task completion drives 60% of score
    base = completion_rate * 0.60

    # Research is important: adds up to 0.15
    research_bonus = 0.15 if has_research else 0.0

    # Execution plan: adds 0.12 (workflow ready)
    plan_bonus = 0.12 if has_execution_plan else 0.0

    # Approved decisions add a small trust bonus (max 0.08)
    decision_bonus = 0.08 if has_decisions else 0.0

    # Failures deduct from score: 0.10 per failure, max 0.25
    failure_penalty = min(0.25, failed_tasks * 0.10)

    # Blockers reduce score significantly: 0.10 per blocker, max 0.30
    blocker_penalty = min(0.30, blocker_count * 0.10)

    # Missing info reduces score: 0.05 per gap, max 0.20
    missing_penalty = min(0.20, missing_info_count * 0.05)

    raw = base + research_bonus + plan_bonus + decision_bonus - failure_penalty - blocker_penalty - missing_penalty
    return round(max(0.0, min(1.0, raw)), 3)


def score_from_context(ctx: MissionContext, blocker_count: int = 0, missing_info_count: int = 0) -> ReadinessDetail:
    """
    Compute readiness from a MissionContext.
    blocker_count and missing_info_count are supplied by the engine
    (computed after blocker detection and gap analysis).
    """
    total     = ctx.task_count
    completed = sum(1 for ts in ctx.task_summaries if ts["state"] == "COMPLETED")
    failed    = sum(1 for ts in ctx.task_summaries if ts["state"] == "FAILED")
    has_research  = any(ts["has_research"]  for ts in ctx.task_summaries)
    has_plan      = any(ts["has_plan"]      for ts in ctx.task_summaries)
    has_decisions = len(ctx.memory.decisions) > 0

    completion_rate = completed / total if total > 0 else 0.0

    score_val = compute(
        total_tasks=total,
        completed_tasks=completed,
        failed_tasks=failed,
        has_research=has_research,
        has_execution_plan=has_plan,
        has_decisions=has_decisions,
        blocker_count=blocker_count,
        missing_info_count=missing_info_count,
    )

    return ReadinessDetail(
        total_tasks=total,
        completed_tasks=completed,
        failed_tasks=failed,
        has_research=has_research,
        has_execution_plan=has_plan,
        has_decisions=has_decisions,
        blocker_count=blocker_count,
        missing_info_count=missing_info_count,
        completion_rate=completion_rate,
        score=score_val,
    )
