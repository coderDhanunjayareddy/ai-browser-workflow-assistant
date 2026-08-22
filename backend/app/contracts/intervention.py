from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.contracts.base import VersionedContract
from app.contracts.versions import HUMAN_INTERVENTION_REQUEST_V1, HUMAN_INTERVENTION_RESUME_V1


InterventionKind = Literal[
    "authentication",
    "mfa",
    "captcha",
    "privileged_ui",
    "sensitive_input",
    "consequential_confirmation",
    "identity_ambiguity",
    "external_authorization",
    "external_blocker",
]
InterventionState = Literal["awaiting_user", "satisfied", "expired", "cancelled", "blocked"]
SecretHandling = Literal["direct_browser_only", "non_sensitive_response_allowed", "no_user_data_required"]
ResumeEvidenceKind = Literal[
    "url_matches",
    "origin_matches",
    "element_visible",
    "element_absent",
    "authenticated_state",
    "authorization_granted",
    "dialog_closed",
    "user_acknowledged",
]


class ResumeCondition(BaseModel):
    evidence_kind: ResumeEvidenceKind
    expected_value: str = Field(min_length=1, max_length=2048)
    target_role: str | None = Field(default=None, max_length=100)
    target_name: str | None = Field(default=None, max_length=500)
    observed_origin: str = Field(min_length=1, max_length=2048)
    tab_id: int = Field(ge=0)
    frame_id: str = Field(default="top", min_length=1, max_length=300)


class HumanInterventionRequest(VersionedContract):
    schema_version: str = HUMAN_INTERVENTION_REQUEST_V1
    producer: str = "backend.generic_capability_kernel"
    intervention_id: str = Field(min_length=1, max_length=300)
    mission_id: str = Field(min_length=1, max_length=300)
    objective_id: str = Field(min_length=1, max_length=300)
    kind: InterventionKind
    reason_code: str = Field(min_length=1, max_length=200)
    user_message: str = Field(min_length=1, max_length=1000)
    requested_action: str = Field(min_length=1, max_length=1000)
    secret_handling: SecretHandling
    checkpoint_ref: str = Field(min_length=1, max_length=500)
    completed_objective_ids: list[str] = Field(default_factory=list, max_length=500)
    pending_objective_ids: list[str] = Field(default_factory=list, max_length=500)
    resume_condition: ResumeCondition
    request_budget: int = Field(default=1, ge=1, le=2)
    unchanged_gate_attempts: int = Field(default=0, ge=0, le=2)
    state: InterventionState = "awaiting_user"

    @model_validator(mode="after")
    def validate_boundary(self) -> "HumanInterventionRequest":
        overlap = set(self.completed_objective_ids) & set(self.pending_objective_ids)
        if overlap:
            raise ValueError("Completed and pending objectives must be disjoint.")
        if self.objective_id in self.completed_objective_ids:
            raise ValueError("The blocked objective cannot already be complete.")
        if self.kind in {"authentication", "mfa", "captcha", "sensitive_input"}:
            if self.secret_handling != "direct_browser_only":
                raise ValueError("Sensitive interventions must be completed directly in the browser.")
        return self


class HumanInterventionResume(VersionedContract):
    schema_version: str = HUMAN_INTERVENTION_RESUME_V1
    producer: str = "backend.generic_capability_kernel"
    intervention_id: str = Field(min_length=1, max_length=300)
    checkpoint_ref: str = Field(min_length=1, max_length=500)
    satisfied: bool
    evidence_kind: ResumeEvidenceKind
    observed_value: str = Field(min_length=1, max_length=4096)
    observed_origin: str = Field(min_length=1, max_length=2048)
    tab_id: int = Field(ge=0)
    frame_id: str = Field(default="top", min_length=1, max_length=300)
    resumed_objective_id: str | None = Field(default=None, max_length=300)
    duplicate_dispatch_prevented: bool = True

    @model_validator(mode="after")
    def validate_resume(self) -> "HumanInterventionResume":
        if self.satisfied and not self.resumed_objective_id:
            raise ValueError("A satisfied intervention must name the objective to resume.")
        if not self.duplicate_dispatch_prevented:
            raise ValueError("Intervention resume must preserve exactly-once execution state.")
        return self
