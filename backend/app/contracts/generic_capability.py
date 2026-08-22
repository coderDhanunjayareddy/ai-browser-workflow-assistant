from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.base import VersionedContract
from app.contracts.versions import (
    DURABLE_OBJECTIVE_V1,
    GENERIC_CAPABILITY_REQUEST_V1,
    GENERIC_CAPABILITY_RESULT_V1,
)


CapabilityFamily = Literal[
    "navigation_context",
    "discovery_reading",
    "interaction",
    "content_transfer",
    "consequential_operation",
    "human_intervention",
]
SafetyClass = Literal["safe", "caution", "consequential", "privileged", "blocked"]
ObjectiveState = Literal[
    "pending", "active", "completed", "confirmation_required", "clarification_required",
    "human_intervention_required", "unsupported", "externally_blocked", "safely_failed",
]
TerminalOutcome = Literal[
    "verified_complete", "partially_complete", "confirmation_required", "clarification_required",
    "human_intervention_required", "unsupported", "externally_blocked", "safely_failed",
]


class TargetIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_supplied_identity: str | None = Field(default=None, max_length=1000)
    entity_type: str = Field(min_length=1, max_length=150)
    exact_match_required: bool = False
    allowed_origin: str | None = Field(default=None, max_length=2048)
    tab_id: int | None = Field(default=None, ge=0)
    frame_id: str = Field(default="top", min_length=1, max_length=300)


class ExpectedEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effect_type: str = Field(min_length=1, max_length=150)
    observable_postcondition: str = Field(min_length=1, max_length=1000)
    required_evidence: list[str] = Field(min_length=1, max_length=20)
    no_effect_is_failure: bool = True


class DurableObjective(VersionedContract):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = DURABLE_OBJECTIVE_V1
    producer: str = "backend.generic_capability_kernel"
    mission_id: str = Field(min_length=1, max_length=300)
    objective_id: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=2000)
    required_capabilities: list[str] = Field(min_length=1, max_length=50)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    state: ObjectiveState = "pending"
    completion_evidence_refs: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_objective_state(self) -> "DurableObjective":
        if self.objective_id in self.depends_on:
            raise ValueError("An objective cannot depend on itself.")
        if self.state == "completed" and not self.completion_evidence_refs:
            raise ValueError("A completed objective requires durable verification evidence.")
        return self


class GenericCapabilityRequest(VersionedContract):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = GENERIC_CAPABILITY_REQUEST_V1
    producer: str = "backend.generic_capability_kernel"
    mission_id: str = Field(min_length=1, max_length=300)
    objective_id: str = Field(min_length=1, max_length=300)
    capability_id: str = Field(min_length=1, max_length=300)
    family: CapabilityFamily
    target: TargetIdentity
    inputs: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list, max_length=50)
    expected_effect: ExpectedEffect
    safety_class: SafetyClass
    retry_budget: int = Field(default=0, ge=0, le=2)
    idempotency_key: str = Field(min_length=1, max_length=500)
    confirmation_required: bool = False
    intervention_kinds: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_safety_invariants(self) -> "GenericCapabilityRequest":
        if self.safety_class in {"consequential", "privileged"} and not self.confirmation_required:
            raise ValueError("Consequential and privileged capabilities require confirmation.")
        if self.safety_class in {"consequential", "privileged", "blocked"} and self.retry_budget:
            raise ValueError("Consequential, privileged, or blocked capabilities cannot retry automatically.")
        return self


class GenericCapabilityResult(VersionedContract):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = GENERIC_CAPABILITY_RESULT_V1
    producer: str = "backend.generic_capability_kernel"
    mission_id: str = Field(min_length=1, max_length=300)
    objective_id: str = Field(min_length=1, max_length=300)
    capability_id: str = Field(min_length=1, max_length=300)
    idempotency_key: str = Field(min_length=1, max_length=500)
    outcome: TerminalOutcome
    user_message: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    attempts: int = Field(default=0, ge=0, le=3)
    duplicate_side_effects: int = Field(default=0, ge=0)
    latency_ms: int = Field(ge=0)
    diagnostic_code: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_result_evidence(self) -> "GenericCapabilityResult":
        if self.outcome == "verified_complete" and not self.evidence_refs:
            raise ValueError("Verified completion requires evidence.")
        if self.duplicate_side_effects:
            raise ValueError("A capability result with duplicate side effects cannot be accepted.")
        return self
