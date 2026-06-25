"""
V5.5 Mission Intelligence — MissionBlockerDetector.

Analyzes mission context for conditions that block or degrade execution.

Blocker codes and what they mean:
  NO_TASKS             — mission has no tasks attached (cannot make progress)
  NO_RESEARCH          — no task has produced research; blind execution risk
  FAILED_TASKS         — one or more tasks failed; may require retry
  ABANDONED_TASKS      — tasks were explicitly abandoned
  ACTIVE_TASKS         — some tasks are still in progress (not necessarily a block)
  PENDING_APPROVALS    — human approvals are outstanding (blocks workflow start)
  NO_EXECUTION_PLAN    — no task has produced an execution plan
  MISSING_COMPARISON   — only one research source; recommend comparison
  WORKFLOW_NOT_READY   — workflow preparation step not completed

All detection is pure logic on MissionContext data. No LLM. No DB. <1ms.
"""
from __future__ import annotations

from app.mission.context_registry import MissionContext
from app.mission.intelligence.models import MissionBlocker, BlockerSeverity

# Task states
_TERMINAL = {"COMPLETED", "FAILED", "ABANDONED"}
_ACTIVE   = {"CREATED", "RESEARCHING", "RESEARCH_COMPLETE",
             "READY_FOR_WORKFLOW", "WORKFLOW_RUNNING", "WAITING_APPROVAL"}


def detect(ctx: MissionContext) -> list[MissionBlocker]:
    """
    Return a list of MissionBlockers for the given MissionContext.
    Empty list = no blockers detected.
    """
    blockers: list[MissionBlocker] = []
    summaries = ctx.task_summaries

    # ── B1: No tasks ─────────────────────────────────────────────────────────
    if not summaries:
        blockers.append(MissionBlocker(
            code="NO_TASKS",
            description="Mission has no tasks. Attach at least one task to begin.",
            severity=BlockerSeverity.critical,
        ))
        return blockers  # remaining checks require at least one task

    # ── B2: No research produced by any task ──────────────────────────────────
    if not any(ts["has_research"] for ts in summaries):
        blockers.append(MissionBlocker(
            code="NO_RESEARCH",
            description="No task has completed research. Run research before execution.",
            severity=BlockerSeverity.critical,
        ))

    # ── B3: Failed tasks ──────────────────────────────────────────────────────
    failed_tasks = [ts for ts in summaries if ts["state"] == "FAILED"]
    for ts in failed_tasks:
        blockers.append(MissionBlocker(
            code="FAILED_TASK",
            description=f"Task {ts['task_id']!r} failed and may require retry or replacement.",
            severity=BlockerSeverity.critical,
            task_id=ts["task_id"],
        ))

    # ── B4: Abandoned tasks ───────────────────────────────────────────────────
    abandoned = [ts for ts in summaries if ts["state"] == "ABANDONED"]
    if abandoned:
        ids = ", ".join(ts["task_id"] for ts in abandoned[:3])
        blockers.append(MissionBlocker(
            code="ABANDONED_TASKS",
            description=f"Tasks were abandoned: {ids}. Review and re-attach if needed.",
            severity=BlockerSeverity.warning,
        ))

    # ── B5: Pending approvals ─────────────────────────────────────────────────
    pending_approval_tasks = [ts for ts in summaries if ts.get("approval_count", 0) > 0]
    # Check approvals in MissionContext
    pending_approvals = [a for a in ctx.approvals if a.get("status") == "PENDING"]
    if pending_approvals:
        blockers.append(MissionBlocker(
            code="PENDING_APPROVALS",
            description=f"{len(pending_approvals)} approval(s) are pending. Human must approve before execution.",
            severity=BlockerSeverity.critical,
        ))

    # ── B6: No execution plan ─────────────────────────────────────────────────
    all_terminal = all(ts["state"] in _TERMINAL for ts in summaries)
    if all_terminal and not any(ts["has_plan"] for ts in summaries):
        blockers.append(MissionBlocker(
            code="NO_EXECUTION_PLAN",
            description="All tasks are terminal but no execution plan was produced. Prepare a workflow plan.",
            severity=BlockerSeverity.warning,
        ))

    # ── B7: Only one data source — missing comparison ─────────────────────────
    research_count = sum(1 for ts in summaries if ts["has_research"])
    if research_count == 1 and len(summaries) >= 2:
        blockers.append(MissionBlocker(
            code="MISSING_COMPARISON",
            description="Only one research source available. A comparison task is recommended before execution.",
            severity=BlockerSeverity.warning,
        ))

    # ── B8: Workflow preparation not done ─────────────────────────────────────
    completed_tasks = [ts for ts in summaries if ts["state"] == "COMPLETED"]
    has_plan = any(ts["has_plan"] for ts in completed_tasks)
    if completed_tasks and not has_plan:
        blockers.append(MissionBlocker(
            code="WORKFLOW_NOT_READY",
            description="Tasks completed but no workflow execution plan found. Prepare workflow before launch.",
            severity=BlockerSeverity.warning,
        ))

    return blockers
