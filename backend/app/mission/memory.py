"""
V5.0 Mission Layer — MissionMemory.

Aggregates entities, goals, research findings, execution plans, and approved
decisions from ALL tasks in a mission.

Computed on demand — NO separate DB table.
Data sources: UnifiedTask.entities, .current_goal, .research_report,
              .execution_plan, .approvals (for decisions).

Merge strategy:
  entities  → later-attached tasks override earlier ones (dict update order)
  goals     → union (deduplicated list)
  findings  → list per task (most recent first)
  decisions → only ApprovalRecord with status=APPROVED
"""
from __future__ import annotations

import time
from typing import Optional

from app.mission.models import Mission, MissionMemory
from app.unified.models import UnifiedTask, ApprovalStatus


def build(mission: Mission, tasks: list[UnifiedTask]) -> MissionMemory:
    """
    Build MissionMemory from a list of tasks.
    Tasks should be ordered oldest-first (same as mission.task_ids order).
    """
    merged_entities: dict = {}
    goals: list[str] = []
    research_findings: list[dict] = []
    execution_plans: list[dict] = []
    decisions: list[dict] = []

    for task in tasks:
        # Merge entities (later tasks win on key conflict)
        if task.entities:
            merged_entities.update(task.entities)

        # Collect goals (deduplicated, preserve order)
        if task.current_goal and task.current_goal not in goals:
            goals.append(task.current_goal)

        # Collect research findings
        if task.research_report:
            research_findings.append({
                "task_id": task.task_id,
                "query":   task.original_query,
                "summary": task.research_report.get("executive_summary", ""),
                "findings": task.research_report.get("key_findings", []),
                "confidence": task.research_report.get("confidence_score", 0.0),
            })

        # Collect execution plans
        if task.execution_plan:
            execution_plans.append({
                "task_id":       task.task_id,
                "workflow_type": task.execution_plan.get("workflow_type", ""),
                "confidence":    task.execution_plan.get("confidence", 0.0),
                "plan":          task.execution_plan,
            })

        # Collect approved decisions
        for approval in task.approvals:
            if approval.status == ApprovalStatus.approved:
                decisions.append({
                    "task_id":     task.task_id,
                    "action":      approval.action,
                    "risk_level":  approval.risk_level,
                    "resolved_at": approval.resolved_at.isoformat()
                                   if approval.resolved_at else None,
                    "note":        approval.resolution_note,
                })

    return MissionMemory(
        mission_id=mission.mission_id,
        entities=merged_entities,
        goals=goals,
        research_findings=list(reversed(research_findings)),  # most recent first
        execution_plans=list(reversed(execution_plans)),
        decisions=decisions,
    )


def build_by_id(mission_id: str) -> Optional[MissionMemory]:
    """Convenience: look up mission + tasks from stores, then build memory."""
    from app.mission import store as mission_store
    from app.unified import store as task_store

    mission = mission_store.get(mission_id)
    if mission is None:
        return None
    tasks = [t for tid in mission.task_ids if (t := task_store.get(tid)) is not None]
    return build(mission, tasks)


def to_dict(memory: MissionMemory) -> dict:
    """Convert MissionMemory to a JSON-serializable dict."""
    return {
        "mission_id":        memory.mission_id,
        "entities":          memory.entities,
        "goals":             memory.goals,
        "research_findings": memory.research_findings,
        "execution_plans":   memory.execution_plans,
        "decisions":         memory.decisions,
        "last_updated":      memory.last_updated.isoformat(),
    }
