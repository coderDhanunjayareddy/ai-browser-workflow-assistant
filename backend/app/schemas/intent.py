from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


IntentLedgerStatus = Literal[
    "QUEUED",
    "DISPATCHED",
    "EXECUTING",
    "WAITING_PROVIDER",
    "WAITING_BROWSER",
    "WAITING_USER",
    "WAITING_EXTERNAL",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
    "CANCELLED",
    "SKIPPED",
    "PARTIAL",
]


class IntentDTO(BaseModel):
    intent_id: str
    mission_id: str
    parent_intent_id: str | None = None
    intent: str
    provider: str
    capability: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    blueprint_id: str | None = None
    blueprint_node_id: str | None = None
    blueprint_revision: int | None = None


class IntentNextRequest(BaseModel):
    mission_id: str
    provider: str | None = None


class IntentNextResponse(BaseModel):
    intent: IntentDTO | None = None
    status: str
    reason: str


class IntentEvidence(BaseModel):
    evidence_type: str = "provider_execution"
    success: bool
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    browser_metadata: dict[str, Any] = Field(default_factory=dict)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    runtime_resource_updates: list[dict[str, Any]] = Field(default_factory=list)


class IntentUpdateRequest(BaseModel):
    mission_id: str
    intent_id: str
    outcome: Literal["success", "failure", "blocked", "cancelled", "partial"]
    evidence: IntentEvidence
    timestamp_ms: int | None = None


class IntentUpdateResponse(BaseModel):
    updated: bool
    intent: IntentDTO
    next_intent: IntentDTO | None = None
    status: str
    reason: str
