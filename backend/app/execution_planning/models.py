"""
V9.0 Execution Planning Layer — Domain Models.

This layer performs NO browser execution. It produces deterministic ExecutionPlans
that a FUTURE Execution Gateway (V9.5+) will consume. The Gateway may ONLY accept an
ExecutionPlan with status READY, and it must NEVER invent steps — it only dispatches
the steps already present in an approved plan.

Models:
  PlanStatus          : plan lifecycle state
  ExecutionMode       : how the plan is meant to be run (planning descriptor only)
  ActionType          : the kind of action a step describes (NOT browser code)
  TargetType          : what a step targets
  ValidationStrategy  : how a step's success would be verified
  RollbackAction      : rollback descriptor enum (metadata only)
  ExecutionStep       : one ordered planning step
  ExecutionPlan       : an ordered set of steps tied to one ExecutionAuthorization
  PlanValidationResult: output of the PlanValidator
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

PLANNER_VERSION: str = "1.0"


# ── Plan lifecycle ────────────────────────────────────────────────────────────

class PlanStatus(str, Enum):
    draft     = "DRAFT"        # created, not yet validated
    ready     = "READY"        # validated — the ONLY status the Gateway may accept
    executing = "EXECUTING"    # future (gateway) — never set in V9.0
    completed = "COMPLETED"    # future (gateway) — never set in V9.0
    failed    = "FAILED"       # future (gateway) — never set in V9.0
    aborted   = "ABORTED"      # cancelled / archived before execution


# Statuses that the V9.0 planning layer is allowed to assign itself.
PLANNING_ASSIGNABLE_STATUSES: frozenset[PlanStatus] = frozenset({
    PlanStatus.draft, PlanStatus.ready, PlanStatus.aborted,
})

# Reserved for the future Execution Gateway — V9.0 never assigns these.
GATEWAY_ONLY_STATUSES: frozenset[PlanStatus] = frozenset({
    PlanStatus.executing, PlanStatus.completed, PlanStatus.failed,
})


# ── Execution mode (planning descriptor only) ─────────────────────────────────

class ExecutionMode(str, Enum):
    sequential = "SEQUENTIAL"   # run steps in order, stop on failure
    atomic     = "ATOMIC"       # all-or-nothing (rollback all on any failure)
    dry_run    = "DRY_RUN"      # gateway should simulate, never act


VALID_EXECUTION_MODES: frozenset[ExecutionMode] = frozenset(ExecutionMode)


# ── Action / target / validation descriptors ──────────────────────────────────

class ActionType(str, Enum):
    navigate = "NAVIGATE"
    read     = "READ"
    extract  = "EXTRACT"
    input    = "INPUT"
    click    = "CLICK"
    scroll   = "SCROLL"
    wait     = "WAIT"
    validate = "VALIDATE"


class TargetType(str, Enum):
    url     = "URL"
    element = "ELEMENT"
    page    = "PAGE"
    tab     = "TAB"
    form    = "FORM"
    region  = "REGION"


class ValidationStrategy(str, Enum):
    dom_presence = "DOM_PRESENCE"
    url_match    = "URL_MATCH"
    text_match   = "TEXT_MATCH"
    manual       = "MANUAL"
    none         = "NONE"


class RollbackAction(str, Enum):
    navigate_back  = "NAVIGATE_BACK"
    clear_input    = "CLEAR_INPUT"
    scroll_restore = "SCROLL_RESTORE"
    manual_review  = "MANUAL_REVIEW"
    none           = "NONE"


# Per-action planning metadata: default duration (ms), validation, rollback.
ACTION_PROFILE: dict[ActionType, dict[str, Any]] = {
    ActionType.navigate: {"duration_ms": 800,  "validation": ValidationStrategy.url_match,    "rollback": RollbackAction.navigate_back,  "mutating": True},
    ActionType.read:     {"duration_ms": 300,  "validation": ValidationStrategy.dom_presence, "rollback": RollbackAction.none,           "mutating": False},
    ActionType.extract:  {"duration_ms": 400,  "validation": ValidationStrategy.dom_presence, "rollback": RollbackAction.none,           "mutating": False},
    ActionType.input:    {"duration_ms": 500,  "validation": ValidationStrategy.dom_presence, "rollback": RollbackAction.clear_input,    "mutating": True},
    ActionType.click:    {"duration_ms": 600,  "validation": ValidationStrategy.dom_presence, "rollback": RollbackAction.manual_review,  "mutating": True},
    ActionType.scroll:   {"duration_ms": 200,  "validation": ValidationStrategy.none,         "rollback": RollbackAction.scroll_restore, "mutating": True},
    ActionType.wait:     {"duration_ms": 1000, "validation": ValidationStrategy.none,         "rollback": RollbackAction.none,           "mutating": False},
    ActionType.validate: {"duration_ms": 250,  "validation": ValidationStrategy.text_match,   "rollback": RollbackAction.none,           "mutating": False},
}

# Actions that mutate page state and therefore REQUIRE a rollback action defined.
MUTATING_ACTIONS: frozenset[ActionType] = frozenset(
    at for at, prof in ACTION_PROFILE.items() if prof["mutating"]
)


# ── ExecutionStep ─────────────────────────────────────────────────────────────

@dataclass
class ExecutionStep:
    step_id:             str
    order:               int
    action_type:         ActionType
    target_type:         TargetType
    target_description:  str
    parameters:          dict[str, Any]     = field(default_factory=dict)
    expected_result:     str                = ""
    validation_strategy: ValidationStrategy = ValidationStrategy.none
    rollback_action:     RollbackAction     = RollbackAction.none
    approval_scope:      str                = ""

    @property
    def is_mutating(self) -> bool:
        return self.action_type in MUTATING_ACTIONS

    @property
    def requires_rollback(self) -> bool:
        return self.is_mutating

    @property
    def has_rollback(self) -> bool:
        return self.rollback_action != RollbackAction.none

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id":             self.step_id,
            "order":               self.order,
            "action_type":         self.action_type.value,
            "target_type":         self.target_type.value,
            "target_description":  self.target_description,
            "parameters":          self.parameters,
            "expected_result":     self.expected_result,
            "validation_strategy": self.validation_strategy.value,
            "rollback_action":     self.rollback_action.value,
            "approval_scope":      self.approval_scope,
            "is_mutating":         self.is_mutating,
            "requires_rollback":   self.requires_rollback,
            "has_rollback":        self.has_rollback,
        }


def make_step(
    order:              int,
    action_type:        ActionType,
    target_type:        TargetType,
    target_description: str,
    *,
    parameters:          Optional[dict] = None,
    expected_result:     str = "",
    validation_strategy: Optional[ValidationStrategy] = None,
    rollback_action:     Optional[RollbackAction] = None,
    approval_scope:      str = "",
) -> ExecutionStep:
    profile = ACTION_PROFILE[action_type]
    return ExecutionStep(
        step_id             = f"step-{str(uuid.uuid4())[:12]}",
        order               = order,
        action_type         = action_type,
        target_type         = target_type,
        target_description  = target_description,
        parameters          = parameters or {},
        expected_result     = expected_result,
        validation_strategy = validation_strategy if validation_strategy is not None else profile["validation"],
        rollback_action     = rollback_action if rollback_action is not None else profile["rollback"],
        approval_scope      = approval_scope,
    )


# ── ExecutionPlan ─────────────────────────────────────────────────────────────

@dataclass
class ExecutionPlan:
    plan_id:               str
    authorization_id:      str
    mission_id:            Optional[str]
    task_id:               Optional[str]
    created_at:            float
    planner_version:       str
    execution_mode:        ExecutionMode
    estimated_steps:       int
    estimated_duration_ms: int
    rollback_supported:    bool
    confidence:            float
    status:                PlanStatus            = PlanStatus.draft
    steps:                 list[ExecutionStep]   = field(default_factory=list)
    metadata:              dict[str, Any]        = field(default_factory=dict)
    validated_at:          Optional[float]       = None
    archived_at:           Optional[float]       = None
    superseded_by:         Optional[str]         = None

    @property
    def is_ready(self) -> bool:
        return self.status == PlanStatus.ready

    @property
    def is_archived(self) -> bool:
        return self.status == PlanStatus.aborted

    @property
    def mutating_step_count(self) -> int:
        return sum(1 for s in self.steps if s.is_mutating)

    def to_dict(self, include_steps: bool = True) -> dict[str, Any]:
        d = {
            "plan_id":               self.plan_id,
            "authorization_id":      self.authorization_id,
            "mission_id":            self.mission_id,
            "task_id":               self.task_id,
            "created_at":            self.created_at,
            "planner_version":       self.planner_version,
            "execution_mode":        self.execution_mode.value,
            "estimated_steps":       self.estimated_steps,
            "estimated_duration_ms": self.estimated_duration_ms,
            "rollback_supported":    self.rollback_supported,
            "confidence":            self.confidence,
            "status":                self.status.value,
            "mutating_step_count":   self.mutating_step_count,
            "metadata":              self.metadata,
            "validated_at":          self.validated_at,
            "archived_at":           self.archived_at,
            "superseded_by":         self.superseded_by,
            "is_ready":              self.is_ready,
        }
        if include_steps:
            d["steps"] = [s.to_dict() for s in self.steps]
        return d


def make_plan(
    authorization_id:      str,
    *,
    mission_id:            Optional[str],
    task_id:               Optional[str],
    created_at:            float,
    execution_mode:        ExecutionMode,
    steps:                 list[ExecutionStep],
    estimated_duration_ms: int,
    rollback_supported:    bool,
    confidence:            float,
    metadata:              Optional[dict] = None,
) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id               = f"plan-{str(uuid.uuid4())[:12]}",
        authorization_id      = authorization_id,
        mission_id            = mission_id,
        task_id               = task_id,
        created_at            = created_at,
        planner_version       = PLANNER_VERSION,
        execution_mode        = execution_mode,
        estimated_steps       = len(steps),
        estimated_duration_ms = estimated_duration_ms,
        rollback_supported    = rollback_supported,
        confidence            = confidence,
        status                = PlanStatus.draft,
        steps                 = steps,
        metadata              = metadata or {},
    )


# ── PlanValidationResult ──────────────────────────────────────────────────────

@dataclass
class PlanValidationResult:
    plan_id:      str
    valid:        bool
    checks:       dict[str, bool]
    errors:       list[str]
    validated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id":      self.plan_id,
            "valid":        self.valid,
            "checks":       self.checks,
            "errors":       self.errors,
            "validated_at": self.validated_at,
        }
