"""
V9.0 Execution Planning Layer — Pydantic API Schemas.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class ExecutionStepSchema(BaseModel):
    step_id:             str
    order:               int
    action_type:         str
    target_type:         str
    target_description:  str
    parameters:          dict[str, Any] = Field(default_factory=dict)
    expected_result:     str            = ""
    validation_strategy: str            = "NONE"
    rollback_action:     str            = "NONE"
    approval_scope:      str            = ""
    is_mutating:         bool           = False
    requires_rollback:   bool           = False
    has_rollback:        bool           = False


class ExecutionPlanSchema(BaseModel):
    plan_id:               str
    authorization_id:      str
    mission_id:            Optional[str] = None
    task_id:               Optional[str] = None
    created_at:            float         = 0.0
    planner_version:       str           = "1.0"
    execution_mode:        str           = "SEQUENTIAL"
    estimated_steps:       int           = 0
    estimated_duration_ms: int           = 0
    rollback_supported:    bool          = False
    confidence:            float         = 0.0
    status:                str           = "DRAFT"
    mutating_step_count:   int           = 0
    metadata:              dict[str, Any] = Field(default_factory=dict)
    validated_at:          Optional[float] = None
    archived_at:           Optional[float] = None
    superseded_by:         Optional[str] = None
    is_ready:              bool          = False
    steps:                 list[ExecutionStepSchema] = Field(default_factory=list)


class PlanValidationResultSchema(BaseModel):
    plan_id:      str
    valid:        bool
    checks:       dict[str, bool] = Field(default_factory=dict)
    errors:       list[str]       = Field(default_factory=list)
    validated_at: float           = 0.0


class PlanAnalyticsSchema(BaseModel):
    plans_created:       int   = 0
    plans_validated:     int   = 0
    validation_failures: int   = 0
    avg_steps:           float = 0.0
    avg_duration_ms:     float = 0.0
    rollback_supported:  int   = 0
    archived:            int   = 0


class PlanInspectorSchema(BaseModel):
    plan_id:          str
    plan:             dict           = Field(default_factory=dict)
    step_count:       int            = 0
    mutating_steps:   int            = 0
    rollback:         dict           = Field(default_factory=dict)
    validation:       dict           = Field(default_factory=dict)
    authorization:    Optional[dict] = None
    mission_context:  Optional[dict] = None
    timeline_summary: Optional[dict] = None
    analytics:        dict           = Field(default_factory=dict)
    registry_stats:   dict           = Field(default_factory=dict)
    latency_ms:       float          = 0.0


class PlanSummarySchema(BaseModel):
    total_plans:    int           = 0
    ready_plans:    int           = 0
    draft_plans:    int           = 0
    archived_plans: int           = 0
    active_plan_id: Optional[str] = None
    plan_ids:       list[str]     = Field(default_factory=list)
