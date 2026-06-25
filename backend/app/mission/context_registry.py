"""
V5.0 Mission Layer — MissionContextRegistry.

Single-call aggregation of all mission context.
Avoids querying each task separately by reading from the in-memory store.

Returns MissionContext: a rich snapshot including task summaries, merged entities,
goals, research findings, execution plans, approvals, and MissionMemory.

All computation is pure in-memory — no DB or AI calls. < 20ms p95.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from app.mission.models import Mission, MissionMemory
from app.unified.models import UnifiedTask


@dataclass
class MissionContext:
    mission_id:       str
    mission_title:    str
    mission_state:    str
    priority:         int
    task_count:       int
    task_summaries:   list[dict]    # [{task_id, state, query, goal, has_research, has_plan}]
    entities:         dict
    goals:            list[str]
    research_findings: list[dict]
    execution_plans:  list[dict]
    approvals:        list[dict]
    memory:           MissionMemory
    latency_ms:       int = 0


def get_context(mission_id: str) -> Optional[MissionContext]:
    """
    Aggregate all mission context in one call.

    Returns None if the mission is not in the in-memory store.
    """
    from app.mission import store as mission_store
    from app.unified import store as task_store
    from app.mission import memory as mission_memory

    t0 = time.perf_counter()

    mission = mission_store.get(mission_id)
    if mission is None:
        return None

    tasks: list[UnifiedTask] = [
        t for tid in mission.task_ids if (t := task_store.get(tid)) is not None
    ]

    # Task summaries
    task_summaries = [
        {
            "task_id":      t.task_id,
            "state":        t.state.value,
            "query":        t.original_query,
            "goal":         t.current_goal,
            "has_research": t.research_report is not None,
            "has_plan":     t.execution_plan is not None,
            "approval_count": len(t.approvals),
        }
        for t in tasks
    ]

    # Aggregate approvals across all tasks
    all_approvals = [
        {
            "task_id":    t.task_id,
            "action":     a.action,
            "risk_level": a.risk_level,
            "status":     a.status.value,
            "note":       a.resolution_note,
        }
        for t in tasks
        for a in t.approvals
    ]

    mem = mission_memory.build(mission, tasks)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    return MissionContext(
        mission_id=mission.mission_id,
        mission_title=mission.title,
        mission_state=mission.state.value,
        priority=mission.priority,
        task_count=len(tasks),
        task_summaries=task_summaries,
        entities=mem.entities,
        goals=mem.goals,
        research_findings=mem.research_findings,
        execution_plans=mem.execution_plans,
        approvals=all_approvals,
        memory=mem,
        latency_ms=latency_ms,
    )


def get_context_dict(mission_id: str) -> Optional[dict]:
    """Convenience wrapper that returns a serializable dict."""
    ctx = get_context(mission_id)
    if ctx is None:
        return None
    from app.mission.memory import to_dict as memory_to_dict
    return {
        "mission_id":        ctx.mission_id,
        "mission_title":     ctx.mission_title,
        "mission_state":     ctx.mission_state,
        "priority":          ctx.priority,
        "task_count":        ctx.task_count,
        "task_summaries":    ctx.task_summaries,
        "entities":          ctx.entities,
        "goals":             ctx.goals,
        "research_findings": ctx.research_findings,
        "execution_plans":   ctx.execution_plans,
        "approvals":         ctx.approvals,
        "memory":            memory_to_dict(ctx.memory),
        "latency_ms":        ctx.latency_ms,
    }
