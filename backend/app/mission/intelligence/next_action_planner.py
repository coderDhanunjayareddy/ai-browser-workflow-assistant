"""
V5.5 Mission Intelligence — MissionNextActionPlanner.

Determines the single most important next action for a mission.

Decision rules (evaluated in priority order):
  1. Critical blockers exist      → Resolve the first critical blocker
  2. No tasks at all              → Attach research task
  3. Pending approvals            → Review pending approvals
  4. No research complete         → Continue research
  5. Only 1 research source       → Compare options
  6. Failed tasks exist           → Retry failed task
  7. All tasks done, no plan      → Prepare workflow execution plan
  8. Plan exists, all done        → Launch workflow (advisory)
  9. Active tasks in progress     → Monitor active tasks
  10. Default                     → Review mission status

All rules are deterministic. No LLM. < 0.5ms.
"""
from __future__ import annotations

from app.mission.context_registry import MissionContext
from app.mission.intelligence.models import (
    MissionBlocker, BlockerSeverity, MissionNextAction,
)


def plan(
    ctx: MissionContext,
    blockers: list[MissionBlocker],
    readiness_score: float,
) -> MissionNextAction:
    """
    Return the single recommended next action given the mission context and blockers.
    """
    summaries = ctx.task_summaries

    # ── Rule 1: Critical blockers ─────────────────────────────────────────────
    critical = [b for b in blockers if b.severity == BlockerSeverity.critical]
    if critical:
        first = critical[0]
        return MissionNextAction(
            action="Resolve blocker",
            reasoning=first.description,
            priority=1,
        )

    # ── Rule 2: No tasks ──────────────────────────────────────────────────────
    if not summaries:
        return MissionNextAction(
            action="Attach a research task",
            reasoning="Mission has no tasks. Add a research task to begin gathering information.",
            priority=1,
        )

    # ── Rule 3: Pending approvals ─────────────────────────────────────────────
    pending_approvals = [a for a in ctx.approvals if a.get("status") == "PENDING"]
    if pending_approvals:
        return MissionNextAction(
            action="Review pending approvals",
            reasoning=f"{len(pending_approvals)} approval(s) are waiting for human review.",
            priority=1,
        )

    # ── Rule 4: No research produced ─────────────────────────────────────────
    has_research = any(ts["has_research"] for ts in summaries)
    if not has_research:
        active_tasks = [ts for ts in summaries if ts["state"] not in {"COMPLETED", "FAILED", "ABANDONED"}]
        if active_tasks:
            return MissionNextAction(
                action="Continue research",
                reasoning="Research is in progress. Wait for current research tasks to complete.",
                priority=2,
            )
        return MissionNextAction(
            action="Start research",
            reasoning="No research has been completed. Begin a research task to gather information.",
            priority=1,
        )

    # ── Rule 5: Failed tasks ──────────────────────────────────────────────────
    failed_tasks = [ts for ts in summaries if ts["state"] == "FAILED"]
    if failed_tasks:
        return MissionNextAction(
            action="Retry or replace failed task",
            reasoning=f"Task {failed_tasks[0]['task_id']!r} failed. Investigate and retry.",
            priority=1,
        )

    # ── Rule 6: Only one research source and no plan yet ─────────────────────
    research_count = sum(1 for ts in summaries if ts["has_research"])
    has_plan     = any(ts["has_plan"] for ts in summaries)
    all_terminal = all(ts["state"] in {"COMPLETED", "FAILED", "ABANDONED"} for ts in summaries)
    if research_count == 1 and all_terminal and not has_plan:
        return MissionNextAction(
            action="Compare options",
            reasoning="Only one data source available. Add a comparison task before making a decision.",
            priority=2,
        )

    # ── Rule 7: All tasks done, no execution plan ─────────────────────────────
    if all_terminal and not has_plan:
        return MissionNextAction(
            action="Prepare workflow execution plan",
            reasoning="All tasks are complete but no execution plan has been produced. Build a workflow plan.",
            priority=2,
        )

    # ── Rule 8: Plan ready, all tasks done → launch ───────────────────────────
    if all_terminal and has_plan and readiness_score >= 0.80:
        return MissionNextAction(
            action="Open workflow",
            reasoning=(
                f"Research complete and execution plan ready (readiness {readiness_score:.0%}). "
                "Human can now initiate the workflow."
            ),
            priority=1,
        )

    # ── Rule 9: Active tasks in progress ────────────────────────────────────
    active_tasks = [ts for ts in summaries if ts["state"] not in {"COMPLETED", "FAILED", "ABANDONED"}]
    if active_tasks:
        return MissionNextAction(
            action="Monitor active tasks",
            reasoning=f"{len(active_tasks)} task(s) still in progress. Wait for completion before launching workflow.",
            priority=3,
        )

    # ── Rule 10: Default ─────────────────────────────────────────────────────
    return MissionNextAction(
        action="Review mission status",
        reasoning=(
            f"Mission readiness is {readiness_score:.0%}. "
            "Review tasks and ensure all required information is present."
        ),
        priority=2,
    )
