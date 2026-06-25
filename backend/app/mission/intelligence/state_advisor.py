"""
V5.5 Mission Intelligence — MissionStateAdvisor.

Recommends what advisory state a mission should be treated as.

ADVISORY ONLY — never mutates MissionState.
The human operator decides whether to act on this recommendation.

Advisory state rules:
  COMPLETED → all tasks completed AND readiness_score >= 0.95
  READY     → readiness_score >= 0.80 AND no critical blockers
  BLOCKED   → any critical blockers OR any FAILED tasks
  PAUSED    → no active tasks AND readiness_score < 0.80 AND no critical blockers
  ACTIVE    → any tasks still in progress (default)
"""
from __future__ import annotations

from app.mission.context_registry import MissionContext
from app.mission.intelligence.models import (
    MissionAdvisoryState, MissionBlocker, BlockerSeverity,
)

_TERMINAL = {"COMPLETED", "FAILED", "ABANDONED"}


def advise(
    ctx: MissionContext,
    blockers: list[MissionBlocker],
    readiness_score: float,
) -> MissionAdvisoryState:
    """
    Return the advisory state for a mission.

    Evaluates rules in priority order. First matching rule wins.
    """
    summaries = ctx.task_summaries
    critical_blockers = [b for b in blockers if b.severity == BlockerSeverity.critical]

    # ── No tasks → default to ACTIVE (mission just started) ──────────────────
    if not summaries:
        return MissionAdvisoryState.active

    failed_tasks    = [ts for ts in summaries if ts["state"] == "FAILED"]
    all_terminal    = all(ts["state"] in _TERMINAL for ts in summaries)
    all_completed   = all(ts["state"] == "COMPLETED" for ts in summaries)
    any_active      = any(ts["state"] not in _TERMINAL for ts in summaries)

    # ── BLOCKED: critical blockers or failed tasks (checked before COMPLETED) ─
    if critical_blockers or failed_tasks:
        return MissionAdvisoryState.blocked

    # ── COMPLETED: all tasks done, high readiness ─────────────────────────────
    if all_completed and readiness_score >= 0.90:
        return MissionAdvisoryState.completed

    # ── READY: high readiness, no critical blockers ───────────────────────────
    if readiness_score >= 0.80 and not critical_blockers:
        return MissionAdvisoryState.ready

    # ── PAUSED: no active tasks but not done or blocked ───────────────────────
    if all_terminal and not all_completed and not critical_blockers:
        return MissionAdvisoryState.paused

    # ── ACTIVE: tasks in progress ─────────────────────────────────────────────
    return MissionAdvisoryState.active
