"""
V4.5 Unified Task Graph — Pydantic API schemas.

Serializable forms of the domain models in app/unified/models.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class TimelineEventSchema(BaseModel):
    event_id:   str
    type:       str             # TimelineEventType.value
    timestamp:  str             # ISO-8601
    data:       dict[str, Any] = Field(default_factory=dict)


class TaskTabSchema(BaseModel):
    tab_id:   str
    url:      str
    title:    str
    role:     str               # TabRole.value
    added_at: str               # ISO-8601


class ApprovalRecordSchema(BaseModel):
    approval_id:     str
    task_id:         str
    action:          str
    risk_level:      str
    status:          str        # ApprovalStatus.value
    created_at:      str        # ISO-8601
    resolved_at:     Optional[str] = None
    resolution_note: str = ""


class UnifiedTaskSchema(BaseModel):
    """API representation of a UnifiedTask."""
    task_id:              str
    conversation_id:      str
    cognitive_session_id: Optional[str] = None
    research_session_id:  Optional[str] = None
    workflow_session_id:  Optional[str] = None
    original_query:       str = ""
    current_goal:         Optional[str] = None
    state:                str             # TaskState.value
    entities:             dict[str, Any] = Field(default_factory=dict)
    execution_plan:       Optional[dict]  = None
    research_report:      Optional[dict]  = None
    approval_state:       str = "PENDING"
    timeline_length:      int = 0
    pending_approvals:    int = 0
    tabs:                 list[TaskTabSchema]        = Field(default_factory=list)
    approvals:            list[ApprovalRecordSchema] = Field(default_factory=list)
    timeline:             list[TimelineEventSchema]  = Field(default_factory=list)
    created_at:           str = ""
    updated_at:           str = ""


class TaskContextSchema(BaseModel):
    """Unified context registry response."""
    task_id:             str
    task_state:          str
    conversation_id:     str
    original_query:      str = ""
    current_goal:        Optional[str] = None
    entities:            dict[str, Any] = Field(default_factory=dict)
    goals:               list[str] = Field(default_factory=list)
    memory_summary:      str = ""
    research_findings:   list[str] = Field(default_factory=list)
    research_topic:      str = ""
    research_confidence: float = 0.0
    workflow_facts:      dict[str, Any] = Field(default_factory=dict)
    execution_plan:      dict[str, Any] = Field(default_factory=dict)
    timeline_length:     int = 0
    pending_approvals:   int = 0
    latency_ms:          int = 0


class TaskAnalyticsSchema(BaseModel):
    total_tasks:                     int = 0
    active_tasks:                    int = 0
    completed_tasks:                 int = 0
    abandoned_tasks:                 int = 0
    failed_tasks:                    int = 0
    research_to_workflow_conversion: int = 0
    research_to_workflow_rate:       float = 0.0
    approval_rate:                   float = 0.0
    average_task_duration_ms:        int = 0
    workflow_completion_rate:        float = 0.0
    workflow_completions:            int = 0
    total_approvals:                 int = 0
    approved_count:                  int = 0
    denied_count:                    int = 0
    timeline_events_recorded:        int = 0
    state_transitions:               dict[str, int] = Field(default_factory=dict)
    # V4.6
    persisted_tasks:                 int = 0
    restored_tasks:                  int = 0
    restoration_hits:                int = 0
    snapshot_count:                  int = 0
    workflow_resumes:                int = 0
    average_restoration_latency_ms:  int = 0
    approval_completion_rate:        float = 0.0
    workflow_resume_rate:            float = 0.0


class TaskSnapshotSchema(BaseModel):
    """API representation of a task snapshot."""
    snapshot_id: str
    trigger:     str
    task_state:  str
    created_at:  str
    context:     dict[str, Any] = Field(default_factory=dict)


class WorkflowPrefillSchema(BaseModel):
    """Prefill payload sent to the workflow panel."""
    task_id:                 str
    title:                   str = ""
    goal:                    Optional[str] = None
    entities:                dict[str, Any] = Field(default_factory=dict)
    execution_plan:          dict[str, Any] = Field(default_factory=dict)
    readiness_state:         str = "NOT_READY"
    approval_classification: str = "REQUIRES_APPROVAL"
    workflow_type:           str = ""
    missing_inputs:          list[str] = Field(default_factory=list)
    recommended_next_action: str = ""
    research_summary:        str = ""
    key_findings:            list[str] = Field(default_factory=list)
    recommended_actions:     list[str] = Field(default_factory=list)
    confidence:              float = 0.0
    pre_filled_facts:        dict[str, Any] = Field(default_factory=dict)
    task_state:              str = "CREATED"
    latency_ms:              int = 0


class TaskRestorationSchema(BaseModel):
    """Response for GET /unified/tasks/{id}/restore."""
    task_id:          str
    restored_from:    str = "memory"  # "memory" | "database"
    task_state:       str
    timeline_events:  int = 0
    approval_count:   int = 0
    snapshot_used:    bool = False
    latency_ms:       int = 0
    original_query:   str = ""
    current_goal:     Optional[str] = None


class WorkflowBootstrapSchema(BaseModel):
    """Bootstrap context for GET /unified/tasks/{id}/bootstrap."""
    task_id:                 str
    original_query:          str = ""
    current_goal:            Optional[str] = None
    entities:                dict[str, Any] = Field(default_factory=dict)
    execution_plan:          dict[str, Any] = Field(default_factory=dict)
    research_summary:        str = ""
    key_findings:            list[str] = Field(default_factory=list)
    recommended_actions:     list[str] = Field(default_factory=list)
    confidence:              float = 0.0
    approval_level:          str = "REQUIRES_APPROVAL"
    workflow_type:           str = ""
    missing_inputs:          list[str] = Field(default_factory=list)
    recommended_next_action: str = ""
    pre_filled_facts:        dict[str, Any] = Field(default_factory=dict)
    is_ready:                bool = False
    latency_ms:              int = 0
