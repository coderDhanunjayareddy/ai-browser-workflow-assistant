"""
V5.0 Mission Layer — Pydantic API Schemas.

Serializable representations of domain models from app/mission/*.
All datetime fields are serialized as ISO-8601 strings.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Core task reference ───────────────────────────────────────────────────────

class MissionTaskRefSchema(BaseModel):
    task_id:     str
    position:    int = 0
    attached_at: str = ""          # ISO-8601


# ── Timeline event ────────────────────────────────────────────────────────────

class MissionTimelineEventSchema(BaseModel):
    event_id:   str
    event_type: str
    mission_id: str
    task_id:    Optional[str] = None
    data:       dict[str, Any] = Field(default_factory=dict)
    timestamp:  str                # ISO-8601


# ── Mission (core) ────────────────────────────────────────────────────────────

class MissionSchema(BaseModel):
    mission_id:  str
    title:       str
    objective:   str
    state:       str               # MissionState.value
    priority:    int = 3
    task_ids:    list[str] = Field(default_factory=list)
    task_count:  int = 0
    metadata:    dict[str, Any] = Field(default_factory=dict)
    created_at:  str = ""          # ISO-8601
    updated_at:  str = ""          # ISO-8601


# ── Memory ────────────────────────────────────────────────────────────────────

class MissionMemorySchema(BaseModel):
    mission_id:        str
    entities:          dict[str, Any] = Field(default_factory=dict)
    goals:             list[str] = Field(default_factory=list)
    research_findings: list[dict] = Field(default_factory=list)
    execution_plans:   list[dict] = Field(default_factory=list)
    decisions:         list[dict] = Field(default_factory=list)
    last_updated:      str = ""    # ISO-8601


# ── Context ───────────────────────────────────────────────────────────────────

class MissionTaskSummarySchema(BaseModel):
    task_id:       str
    state:         str
    query:         str = ""
    goal:          Optional[str] = None
    has_research:  bool = False
    has_plan:      bool = False
    approval_count: int = 0


class MissionContextSchema(BaseModel):
    mission_id:        str
    mission_title:     str
    mission_state:     str
    priority:          int
    task_count:        int
    task_summaries:    list[MissionTaskSummarySchema] = Field(default_factory=list)
    entities:          dict[str, Any] = Field(default_factory=dict)
    goals:             list[str] = Field(default_factory=list)
    research_findings: list[dict] = Field(default_factory=list)
    execution_plans:   list[dict] = Field(default_factory=list)
    approvals:         list[dict] = Field(default_factory=list)
    memory:            MissionMemorySchema
    latency_ms:        int = 0


# ── Analytics ─────────────────────────────────────────────────────────────────

class MissionAnalyticsSchema(BaseModel):
    total_missions:                int = 0
    active_missions:               int = 0
    completed_missions:            int = 0
    failed_missions:               int = 0
    abandoned_missions:            int = 0
    total_tasks_attached:          int = 0
    average_tasks_per_mission:     float = 0.0
    mission_completion_rate:       float = 0.0
    average_mission_duration_ms:   int = 0
    research_to_execution_rate:    float = 0.0


# ── Bootstrap ─────────────────────────────────────────────────────────────────

class MissionBootstrapSchema(BaseModel):
    mission_id:             str
    task_id:                str
    is_ready:               bool = False
    mission_entity_count:   int = 0
    mission_goal_count:     int = 0
    mission_research_count: int = 0
    merged_entities:        dict[str, Any] = Field(default_factory=dict)
    merged_goals:           list[str] = Field(default_factory=list)
    enriched_facts:         dict[str, Any] = Field(default_factory=dict)
    latency_ms:             int = 0


# ── Affinity assignment ───────────────────────────────────────────────────────

class MissionAssignSchema(BaseModel):
    task_id:         str
    mission_id:      str
    mission_title:   str
    was_created:     bool = False
    affinity_score:  Optional[float] = None


# ── Inspector (read-only full view) ───────────────────────────────────────────

class MissionInspectorSchema(BaseModel):
    mission_id:    str
    mission:       MissionSchema
    context:       Optional[MissionContextSchema] = None
    memory:        Optional[MissionMemorySchema] = None
    timeline:      list[MissionTimelineEventSchema] = Field(default_factory=list)
    intelligence:  Optional[dict] = None   # V5.5 advisory intelligence section
    tabs:          Optional[dict] = None   # V6.0 tab coordination section
    trust:         Optional[dict] = None   # V6.5 trust evaluation section
    decisions:     Optional[dict] = None   # V7.5 decision summary
    from_store:    bool = True             # True = in-memory; False = restored from DB
    latency_ms:    int = 0


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateMissionRequest(BaseModel):
    title:     str
    objective: str = ""
    priority:  int = 3
    metadata:  dict[str, Any] = Field(default_factory=dict)


class AssignTaskRequest(BaseModel):
    task_id:         str
    create_if_none:  bool = True
