"""
Phase B — Execution Gateway V1 — Pydantic API Schemas.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class StepExecutionSchema(BaseModel):
    step_id:            str
    order:              int
    action_type:        str
    command_type:       str
    outcome:            str
    attempts:           int
    duration_ms:        float
    validation_passed:  bool
    rollback_performed: bool           = False
    output:             dict[str, Any] = Field(default_factory=dict)
    logs:               list[str]      = Field(default_factory=list)
    message:            str            = ""


class ExecutionRecordSchema(BaseModel):
    execution_id:       str
    plan_id:            str
    authorization_id:   str
    mission_id:         Optional[str] = None
    task_id:            Optional[str] = None
    state:              str
    adapter_name:       str
    created_at:         float          = 0.0
    updated_at:         float          = 0.0
    started_at:         Optional[float] = None
    finished_at:        Optional[float] = None
    current_step_index: int            = 0
    total_steps:        int            = 0
    completed_steps:    int            = 0
    failed_steps:       int            = 0
    remaining_steps:    int            = 0
    total_retries:      int            = 0
    total_duration_ms:  float          = 0.0
    is_terminal:        bool           = False
    rollback_history:   list[dict]     = Field(default_factory=list)
    preflight:          dict           = Field(default_factory=dict)
    metadata:           dict           = Field(default_factory=dict)
    step_executions:    list[StepExecutionSchema] = Field(default_factory=list)


class GatewayAnalyticsSchema(BaseModel):
    executions_started:      int   = 0
    executions_completed:    int   = 0
    executions_failed:       int   = 0
    executions_aborted:      int   = 0
    steps_executed:          int   = 0
    steps_failed:            int   = 0
    total_retries:           int   = 0
    rollbacks_performed:     int   = 0
    total_duration_ms:       float = 0.0
    avg_steps_per_execution: float = 0.0
    avg_duration_ms:         float = 0.0
    success_rate:            float = 0.0


class GatewayInspectorSchema(BaseModel):
    execution_id:       str
    state:              str
    adapter_used:       str
    plan_id:            str
    authorization_id:   str
    current_step:       Optional[dict] = None
    total_steps:        int            = 0
    completed_steps:    int            = 0
    failed_steps:       int            = 0
    remaining_steps:    int            = 0
    execution_history:  list           = Field(default_factory=list)
    retry_history:      list           = Field(default_factory=list)
    rollback_history:   list           = Field(default_factory=list)
    validation_results: list           = Field(default_factory=list)
    audit_trail:        list           = Field(default_factory=list)
    preflight:          dict           = Field(default_factory=dict)
    mission_context:    Optional[dict] = None
    total_retries:      int            = 0
    total_duration_ms:  float          = 0.0
    analytics:          dict           = Field(default_factory=dict)
    registry_stats:     dict           = Field(default_factory=dict)
    audit_stats:        dict           = Field(default_factory=dict)
    latency_ms:         float          = 0.0


class GatewaySummarySchema(BaseModel):
    total_executions:     int           = 0
    running_executions:   int           = 0
    completed_executions: int           = 0
    failed_executions:    int           = 0
    aborted_executions:   int           = 0
    latest_execution_id:  Optional[str] = None
    latest_state:         Optional[str] = None
    execution_ids:        list[str]     = Field(default_factory=list)
