"""
V5.0 Mission Layer — Domain Models.

A Mission groups multiple UnifiedTasks into one coherent objective so the
platform can understand Research → Compare → Decide → Execute as a single
workflow rather than four independent tasks.

Safety: missions only OBSERVE and COORDINATE tasks; they do not execute
anything autonomously. Human remains in control of every action.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── State machine ─────────────────────────────────────────────────────────────

class MissionState(str, Enum):
    created   = "CREATED"
    active    = "ACTIVE"
    paused    = "PAUSED"
    completed = "COMPLETED"
    failed    = "FAILED"
    abandoned = "ABANDONED"


TERMINAL_MISSION_STATES: set[MissionState] = {
    MissionState.completed,
    MissionState.failed,
    MissionState.abandoned,
}

# Allowed forward transitions (incomplete list — lifecycle manager checks these)
VALID_MISSION_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.created:   {MissionState.active, MissionState.abandoned},
    MissionState.active:    {MissionState.paused, MissionState.completed,
                             MissionState.failed, MissionState.abandoned},
    MissionState.paused:    {MissionState.active, MissionState.abandoned},
    MissionState.completed: set(),
    MissionState.failed:    set(),
    MissionState.abandoned: set(),
}


# ── Mission Timeline Event Types ──────────────────────────────────────────────

class MissionEventType(str, Enum):
    mission_created      = "mission_created"
    mission_state_changed = "mission_state_changed"
    task_attached        = "task_attached"
    task_detached        = "task_detached"
    task_completed       = "task_completed"
    task_failed          = "task_failed"
    research_completed   = "research_completed"
    workflow_started     = "workflow_started"
    workflow_completed   = "workflow_completed"
    approval_granted     = "approval_granted"
    approval_denied      = "approval_denied"
    mission_paused       = "mission_paused"
    mission_resumed      = "mission_resumed"
    mission_completed    = "mission_completed"
    mission_failed       = "mission_failed"


# ── Domain dataclasses ────────────────────────────────────────────────────────

@dataclass
class MissionTimelineEvent:
    """One event in the mission-level merged timeline."""
    event_id:   str
    event_type: MissionEventType
    mission_id: str
    task_id:    Optional[str]
    data:       dict
    timestamp:  datetime = field(default_factory=datetime.utcnow)


@dataclass
class MissionMemory:
    """
    Aggregated cross-task context for a mission.
    Computed on demand — not stored in a separate DB table.
    """
    mission_id:         str
    entities:           dict           # merged from all tasks (later tasks override)
    goals:              list[str]      # union of non-null task.current_goal values
    research_findings:  list[dict]     # task.research_report per task that has one
    execution_plans:    list[dict]     # task.execution_plan per task that has one
    decisions:          list[dict]     # approved ApprovalRecord entries across tasks
    last_updated:       datetime = field(default_factory=datetime.utcnow)


@dataclass
class Mission:
    """
    A mission groups multiple UnifiedTasks under one objective.
    mission_id is the primary identifier.
    task_ids is an ordered list (first = earliest attached).
    """
    mission_id:  str
    title:       str
    objective:   str
    state:       MissionState       = MissionState.created
    priority:    int                = 3              # 1 (high) … 5 (low)
    task_ids:    list[str]          = field(default_factory=list)
    metadata:    dict               = field(default_factory=dict)
    created_at:  datetime           = field(default_factory=datetime.utcnow)
    updated_at:  datetime           = field(default_factory=datetime.utcnow)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_MISSION_STATES

    @property
    def task_count(self) -> int:
        return len(self.task_ids)

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()


# ── Factory ────────────────────────────────────────────────────────────────────

def create_mission(
    title: str,
    objective: str = "",
    priority: int = 3,
    mission_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Mission:
    return Mission(
        mission_id=mission_id or str(uuid.uuid4())[:12],
        title=title,
        objective=objective,
        priority=max(1, min(5, priority)),
        metadata=metadata or {},
    )
