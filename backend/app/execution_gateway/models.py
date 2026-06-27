"""
Phase B — Execution Gateway V1 — Domain Models.

The gateway consumes a V9.0 ExecutionPlan and orchestrates its steps through an
adapter. It NEVER touches a browser — it dispatches abstract commands and records
results. The V1 adapter is a deterministic mock.

Models:
  ExecutionState  : lifecycle state of one execution run
  CommandType     : the abstract command the dispatcher emits
  StepOutcome     : per-step result
  ExecutionCommand: a single dispatchable command derived from an ExecutionStep
  AdapterResult   : what an adapter returns for one command
  StepExecution   : the recorded result of executing one step
  AuditEntry      : one row of the audit trail
  RetryConfig     : deterministic retry policy
  ExecutionRecord : the full state of one execution run
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

GATEWAY_VERSION: str = "1.0"


# ── Execution lifecycle state ─────────────────────────────────────────────────

class ExecutionState(str, Enum):
    pending   = "PENDING"     # created, not yet run
    running   = "RUNNING"     # actively dispatching steps
    paused    = "PAUSED"      # manually paused
    completed = "COMPLETED"   # all steps succeeded
    failed    = "FAILED"      # a step failed validation / dispatch
    aborted   = "ABORTED"     # manually aborted


TERMINAL_STATES: frozenset[ExecutionState] = frozenset({
    ExecutionState.completed, ExecutionState.failed, ExecutionState.aborted,
})


# ── Command types (dispatcher emits these) ────────────────────────────────────

class CommandType(str, Enum):
    navigate = "NAVIGATE"
    click    = "CLICK"
    type     = "TYPE"
    wait     = "WAIT"
    extract  = "EXTRACT"
    validate = "VALIDATE"
    upload   = "UPLOAD"
    download = "DOWNLOAD"
    custom   = "CUSTOM"


# ── Per-step outcome ──────────────────────────────────────────────────────────

class StepOutcome(str, Enum):
    success           = "SUCCESS"
    failed            = "FAILED"
    validation_failed = "VALIDATION_FAILED"
    skipped           = "SKIPPED"
    rolled_back       = "ROLLED_BACK"


# ── ExecutionCommand ──────────────────────────────────────────────────────────

@dataclass
class ExecutionCommand:
    command_id:          str
    command_type:        CommandType
    step_id:             str
    order:               int
    target_description:  str
    parameters:          dict[str, Any]
    expected_result:     str
    validation_strategy: str
    rollback_action:     str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id":          self.command_id,
            "command_type":        self.command_type.value,
            "step_id":             self.step_id,
            "order":               self.order,
            "target_description":  self.target_description,
            "parameters":          self.parameters,
            "expected_result":     self.expected_result,
            "validation_strategy": self.validation_strategy,
            "rollback_action":     self.rollback_action,
        }


def make_command(
    command_type:        CommandType,
    step_id:             str,
    order:               int,
    target_description:  str,
    *,
    parameters:          Optional[dict] = None,
    expected_result:     str = "",
    validation_strategy: str = "NONE",
    rollback_action:     str = "NONE",
) -> ExecutionCommand:
    return ExecutionCommand(
        command_id          = f"cmd-{str(uuid.uuid4())[:12]}",
        command_type        = command_type,
        step_id             = step_id,
        order               = order,
        target_description  = target_description,
        parameters          = parameters or {},
        expected_result     = expected_result,
        validation_strategy = validation_strategy,
        rollback_action     = rollback_action,
    )


# ── AdapterResult ─────────────────────────────────────────────────────────────

@dataclass
class AdapterResult:
    success:          bool
    duration_ms:      float
    logs:             list[str]      = field(default_factory=list)
    output:           dict[str, Any] = field(default_factory=dict)
    validation_passed: bool          = True
    message:          str            = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success":           self.success,
            "duration_ms":       self.duration_ms,
            "logs":              self.logs,
            "output":            self.output,
            "validation_passed": self.validation_passed,
            "message":           self.message,
        }


# ── StepExecution ─────────────────────────────────────────────────────────────

@dataclass
class StepExecution:
    step_id:           str
    order:             int
    action_type:       str
    command_type:      str
    outcome:           StepOutcome
    attempts:          int
    duration_ms:       float
    validation_passed: bool
    rollback_performed: bool          = False
    output:            dict[str, Any]  = field(default_factory=dict)
    logs:              list[str]       = field(default_factory=list)
    message:           str             = ""
    started_at:        float           = 0.0
    finished_at:       float           = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id":            self.step_id,
            "order":              self.order,
            "action_type":        self.action_type,
            "command_type":       self.command_type,
            "outcome":            self.outcome.value,
            "attempts":           self.attempts,
            "duration_ms":        self.duration_ms,
            "validation_passed":  self.validation_passed,
            "rollback_performed": self.rollback_performed,
            "output":             self.output,
            "logs":               self.logs,
            "message":            self.message,
            "started_at":         self.started_at,
            "finished_at":        self.finished_at,
        }


# ── AuditEntry ────────────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    entry_id:          str
    execution_id:      str
    step_id:           str
    order:             int
    command_type:      str
    timestamp:         float
    duration_ms:       float
    outcome:           str
    validation_passed: bool
    retry_count:       int
    rollback_performed: bool
    message:           str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id":           self.entry_id,
            "execution_id":       self.execution_id,
            "step_id":            self.step_id,
            "order":              self.order,
            "command_type":       self.command_type,
            "timestamp":          self.timestamp,
            "duration_ms":        self.duration_ms,
            "outcome":            self.outcome,
            "validation_passed":  self.validation_passed,
            "retry_count":        self.retry_count,
            "rollback_performed": self.rollback_performed,
            "message":            self.message,
        }


def make_audit_entry(
    execution_id:      str,
    step_id:           str,
    order:             int,
    command_type:      str,
    timestamp:         float,
    duration_ms:       float,
    outcome:           str,
    validation_passed: bool,
    retry_count:       int,
    rollback_performed: bool = False,
    message:           str = "",
) -> AuditEntry:
    return AuditEntry(
        entry_id           = f"audit-{str(uuid.uuid4())[:12]}",
        execution_id       = execution_id,
        step_id            = step_id,
        order              = order,
        command_type       = command_type,
        timestamp          = timestamp,
        duration_ms        = duration_ms,
        outcome            = outcome,
        validation_passed  = validation_passed,
        retry_count        = retry_count,
        rollback_performed = rollback_performed,
        message            = message,
    )


# ── RetryConfig ───────────────────────────────────────────────────────────────

@dataclass
class RetryConfig:
    max_retries:                int  = 2     # additional attempts after the first
    retry_on_validation_failure: bool = True

    @property
    def max_attempts(self) -> int:
        return self.max_retries + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries":                 self.max_retries,
            "retry_on_validation_failure": self.retry_on_validation_failure,
            "max_attempts":                self.max_attempts,
        }


# ── ExecutionRecord ───────────────────────────────────────────────────────────

@dataclass
class ExecutionRecord:
    execution_id:     str
    plan_id:          str
    authorization_id: str
    mission_id:       Optional[str]
    task_id:          Optional[str]
    state:            ExecutionState
    adapter_name:     str
    created_at:       float
    total_steps:      int
    retry_config:     RetryConfig
    updated_at:       float                 = 0.0
    started_at:       Optional[float]       = None
    finished_at:      Optional[float]       = None
    current_step_index: int                 = 0
    completed_steps:  int                   = 0
    failed_steps:     int                   = 0
    step_executions:  list[StepExecution]   = field(default_factory=list)
    rollback_history: list[dict]            = field(default_factory=list)
    preflight:        dict[str, Any]        = field(default_factory=dict)
    metadata:         dict[str, Any]        = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def remaining_steps(self) -> int:
        return max(0, self.total_steps - self.current_step_index)

    @property
    def total_retries(self) -> int:
        return sum(max(0, s.attempts - 1) for s in self.step_executions)

    @property
    def total_duration_ms(self) -> float:
        return round(sum(s.duration_ms for s in self.step_executions), 3)

    def to_dict(self, include_steps: bool = True) -> dict[str, Any]:
        d = {
            "execution_id":       self.execution_id,
            "plan_id":            self.plan_id,
            "authorization_id":   self.authorization_id,
            "mission_id":         self.mission_id,
            "task_id":            self.task_id,
            "state":              self.state.value,
            "adapter_name":       self.adapter_name,
            "created_at":         self.created_at,
            "updated_at":         self.updated_at,
            "started_at":         self.started_at,
            "finished_at":        self.finished_at,
            "current_step_index": self.current_step_index,
            "total_steps":        self.total_steps,
            "completed_steps":    self.completed_steps,
            "failed_steps":       self.failed_steps,
            "remaining_steps":    self.remaining_steps,
            "total_retries":      self.total_retries,
            "total_duration_ms":  self.total_duration_ms,
            "rollback_history":   self.rollback_history,
            "retry_config":       self.retry_config.to_dict(),
            "preflight":          self.preflight,
            "metadata":           self.metadata,
            "is_terminal":        self.is_terminal,
        }
        if include_steps:
            d["step_executions"] = [s.to_dict() for s in self.step_executions]
        return d


def make_execution(
    plan_id:          str,
    authorization_id: str,
    *,
    mission_id:   Optional[str],
    task_id:      Optional[str],
    total_steps:  int,
    adapter_name: str,
    created_at:   float,
    retry_config: Optional[RetryConfig] = None,
    metadata:     Optional[dict] = None,
) -> ExecutionRecord:
    return ExecutionRecord(
        execution_id     = f"exec-{str(uuid.uuid4())[:12]}",
        plan_id          = plan_id,
        authorization_id = authorization_id,
        mission_id       = mission_id,
        task_id          = task_id,
        state            = ExecutionState.pending,
        adapter_name     = adapter_name,
        created_at       = created_at,
        updated_at       = created_at,
        total_steps      = total_steps,
        retry_config     = retry_config or RetryConfig(),
        metadata         = metadata or {},
    )
