from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


IntentOwner = str
ExecutionStatus = Literal[
    "succeeded",
    "browser_action_required",
    "user_interaction_required",
    "waiting_external",
    "mission_completed",
    "failed",
    "blocked",
]


class IntentOwnership(BaseModel):
    """Resolved owner for a planner intent.

    Ownership is intentionally separate from the planner's browser-action
    schema. Providers can register capabilities without expanding Browser
    Control's action vocabulary.
    """

    owner: IntentOwner
    capability: str
    reason: str
    browser_executable: bool = False


class IntentDispatchDirective(BaseModel):
    schema_version: str = "intent_dispatch.v1"
    intent: str
    owner: IntentOwner
    capability: str
    dispatch_target: str
    browser_executable: bool = False
    reason: str
    payload: dict[str, Any] = Field(default_factory=dict)
    handled: bool = False


class IntentExecutionEvidence(BaseModel):
    evidence_id: str
    source: IntentOwner
    kind: str
    summary: str
    references: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class IntentExecutionResult(BaseModel):
    schema_version: str = "intent_execution.v1"
    intent: str
    owner: IntentOwner
    capability: str
    dispatch_target: str
    status: ExecutionStatus
    reason: str
    evidence: list[IntentExecutionEvidence] = Field(default_factory=list)
    next_intents: list[IntentDispatchDirective] = Field(default_factory=list)
    blocking_reason: str | None = None

    @property
    def success(self) -> bool:
        return self.status in {"succeeded", "mission_completed"}


class IntentQueueResult(BaseModel):
    schema_version: str = "intent_execution_queue.v1"
    mission_id: str
    status: ExecutionStatus
    reason: str
    executions: list[IntentExecutionResult] = Field(default_factory=list)
    evidence: list[IntentExecutionEvidence] = Field(default_factory=list)
    remaining_intents: list[IntentDispatchDirective] = Field(default_factory=list)
    browser_action: dict[str, Any] | None = None
    blocking_reason: str | None = None

    @property
    def success(self) -> bool:
        return self.status in {"succeeded", "mission_completed"}


@dataclass
class ExecutionContext:
    mission_id: str
    task: str
    page_context: Any = None
    prior_steps: list[Any] = field(default_factory=list)
    runtime_state: Any = None
    entity_graph: Any = None
    browser_intelligence: Any = None
    knowledge: Any = None
    validation: Any = None
    mission_plan: Any = None
    success_criteria: Any = None
    completion_state: Any = None
    phase_state: Any = None
    kernel_state: Any = None
    prior_evidence: list[IntentExecutionEvidence] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class IntentExecutorProtocol(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dispatch_target: str
