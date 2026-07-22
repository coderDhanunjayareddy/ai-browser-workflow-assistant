from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.contracts.base import VersionedContract
from app.contracts.versions import VALIDATION_OBJECT_V1
from app.semantic_page.serializers import stable_json


ValidationStatus = Literal["satisfied", "not_satisfied", "contradicted", "uncertain"]
FailureCategory = Literal[
    "action_failed",
    "navigation_failed",
    "missing_target",
    "validation_timeout",
    "unexpected_state",
    "partial_success",
    "unknown",
]


class ValidationEvidence(BaseModel):
    evidence_id: str
    source: str
    kind: str
    value: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationObject(VersionedContract):
    schema_version: str = VALIDATION_OBJECT_V1
    producer: str = "backend.validation"
    validation_id: str = Field(default_factory=lambda: str(uuid4()))
    mission_id: str
    step_id: str
    expected_outcome: str
    observed_outcome: str
    evidence: list[ValidationEvidence] = Field(default_factory=list)
    validation_status: ValidationStatus
    confidence: float = 0.0
    failure_category: FailureCategory | None = None
    required_evidence: list[str] = Field(default_factory=list)
    observed_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    replay_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def status(self) -> ValidationStatus:
        return self.validation_status

    @property
    def sgv_verified(self) -> bool:
        return self.validation_status == "satisfied"

    def to_stable_json(self) -> str:
        data = self.model_dump(mode="json")
        data["created_at"] = "<timestamp>"
        data["validation_id"] = "<validation_id>"
        return stable_json(data)
