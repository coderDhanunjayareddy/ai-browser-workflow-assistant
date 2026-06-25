"""
V4.5 Unified Task Graph — domain models.

Pure Python dataclasses + enums. No Pydantic here.
Pydantic serialization lives in schemas/unified.py (the API boundary).

A UnifiedTask is the single source of truth for one user intention
that may span: conversation → research → intelligence → workflow.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class TaskState(str, Enum):
    """Lifecycle state of a UnifiedTask."""
    created             = "CREATED"
    researching         = "RESEARCHING"
    research_complete   = "RESEARCH_COMPLETE"
    ready_for_workflow  = "READY_FOR_WORKFLOW"
    workflow_running    = "WORKFLOW_RUNNING"
    waiting_approval    = "WAITING_APPROVAL"
    completed           = "COMPLETED"
    failed              = "FAILED"
    abandoned           = "ABANDONED"


class TimelineEventType(str, Enum):
    """Types of events that can appear in a TaskTimeline."""
    user_message        = "user_message"
    assistant_response  = "assistant_response"
    research_started    = "research_started"
    research_completed  = "research_completed"
    workflow_prepared   = "workflow_prepared"
    workflow_started    = "workflow_started"
    workflow_completed  = "workflow_completed"
    approval_requested  = "approval_requested"
    approval_granted    = "approval_granted"
    approval_denied     = "approval_denied"
    failure             = "failure"


class ApprovalStatus(str, Enum):
    """Status of a task-scoped approval record."""
    pending  = "PENDING"
    approved = "APPROVED"
    denied   = "DENIED"
    expired  = "EXPIRED"


class TabRole(str, Enum):
    """Role a browser tab plays in a UnifiedTask."""
    research  = "RESEARCH"
    workflow  = "WORKFLOW"
    approval  = "APPROVAL"
    reference = "REFERENCE"


# ── Timeline ──────────────────────────────────────────────────────────────────

@dataclass
class TimelineEvent:
    """Single event in the unified task timeline."""
    event_id:   str
    event_type: TimelineEventType
    task_id:    str
    data:       dict                         # event-specific payload
    timestamp:  datetime = field(default_factory=datetime.utcnow)


@dataclass
class TaskTimeline:
    """Ordered, chronological sequence of events across all subsystems."""
    task_id: str
    events:  list[TimelineEvent] = field(default_factory=list)

    def append(self, event: TimelineEvent) -> None:
        self.events.append(event)

    def by_type(self, event_type: TimelineEventType) -> list[TimelineEvent]:
        return [e for e in self.events if e.event_type == event_type]


# ── Approval ──────────────────────────────────────────────────────────────────

@dataclass
class ApprovalRecord:
    """Task-scoped approval request (replaces anonymous WorkflowEvent approvals)."""
    approval_id:  str
    task_id:      str
    action:       str
    risk_level:   str                        # "SAFE" | "REQUIRES_APPROVAL" | "HIGH_RISK"
    status:       ApprovalStatus = ApprovalStatus.pending
    created_at:   datetime = field(default_factory=datetime.utcnow)
    resolved_at:  Optional[datetime] = None
    resolution_note: str = ""


# ── Tab registry ──────────────────────────────────────────────────────────────

@dataclass
class TaskTab:
    """One browser tab that participated in a UnifiedTask."""
    tab_id:  str
    url:     str
    title:   str
    role:    TabRole
    added_at: datetime = field(default_factory=datetime.utcnow)


# ── Core Task ─────────────────────────────────────────────────────────────────

@dataclass
class UnifiedTask:
    """
    Single source of truth for one user intention.

    References (by ID) the existing subsystem sessions so nothing is duplicated:
      cognitive_session_id  → CognitiveSession
      research_session_id   → ResearchSession
      workflow_session_id   → WorkflowSession

    Those systems are not replaced; this task is the coordination layer.
    """
    task_id:              str
    conversation_id:      str

    # Cross-system session links
    cognitive_session_id: Optional[str]  = None
    research_session_id:  Optional[str]  = None
    workflow_session_id:  Optional[str]  = None

    # Query + goal context
    original_query:       str            = ""
    current_goal:         Optional[str]  = None

    # State
    state:                TaskState      = TaskState.created
    state_history:        list[tuple[TaskState, datetime]] = field(default_factory=list)

    # Cached context (populated by context registry on demand)
    entities:             dict           = field(default_factory=dict)
    execution_plan:       Optional[dict] = None
    research_report:      Optional[dict] = None
    approval_state:       ApprovalStatus = ApprovalStatus.pending

    # Sub-objects
    timeline:             TaskTimeline   = field(default_factory=lambda: TaskTimeline(task_id=""))
    approvals:            list[ApprovalRecord] = field(default_factory=list)
    tabs:                 list[TaskTab]  = field(default_factory=list)

    # Timestamps
    created_at:           datetime       = field(default_factory=datetime.utcnow)
    updated_at:           datetime       = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.timeline.task_id == "":
            self.timeline = TaskTimeline(task_id=self.task_id)
        if not self.state_history:
            self.state_history = [(self.state, self.created_at)]

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()

    def pending_approvals(self) -> list[ApprovalRecord]:
        return [a for a in self.approvals if a.status == ApprovalStatus.pending]


# ── Lifecycle transition map ──────────────────────────────────────────────────

# Maps (from_state) → set of allowed (to_states)
VALID_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.created:            {TaskState.researching, TaskState.ready_for_workflow, TaskState.abandoned},
    TaskState.researching:        {TaskState.research_complete, TaskState.failed, TaskState.abandoned},
    TaskState.research_complete:  {TaskState.ready_for_workflow, TaskState.abandoned},
    TaskState.ready_for_workflow: {TaskState.workflow_running, TaskState.abandoned},
    TaskState.workflow_running:   {TaskState.waiting_approval, TaskState.completed, TaskState.failed, TaskState.abandoned},
    TaskState.waiting_approval:   {TaskState.workflow_running, TaskState.failed, TaskState.abandoned},
    TaskState.completed:          set(),
    TaskState.failed:             {TaskState.researching, TaskState.ready_for_workflow, TaskState.abandoned},
    TaskState.abandoned:          set(),
}
