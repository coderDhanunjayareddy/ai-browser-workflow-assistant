from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IntentOwner = Literal[
    "browser_control",
    "knowledge_extraction",
    "mission_completion",
    "execution_orchestrator",
    "runtime_state_manager",
    "validation",
    "unknown",
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
    success: bool
    reason: str
    evidence: list[IntentExecutionEvidence] = Field(default_factory=list)
