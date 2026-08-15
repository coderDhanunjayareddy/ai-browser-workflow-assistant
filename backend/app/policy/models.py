from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.contracts.base import VersionedContract
from app.contracts.versions import GOVERNANCE_OBJECT_V1
from app.semantic_page.serializers import stable_json


PolicyDecision = Literal[
    "allow",
    "warn",
    "allow_with_confirmation",
    "block",
    "handoff_required",
    "defer",
]
RiskLevel = Literal["safe", "caution", "danger", "critical"]


class ExecutionConstraints(BaseModel):
    max_retries: int = 3
    execution_timeout_ms: int = 15000
    max_navigation_count: int = 20
    max_download_count: int = 5
    max_upload_count: int = 3
    max_tab_count: int = 20
    rate_limit_per_minute: int = 60
    budget_tokens_remaining: int | None = None


class GovernanceObject(VersionedContract):
    schema_version: str = GOVERNANCE_OBJECT_V1
    producer: str = "backend.policy"
    governance_id: str = Field(default_factory=lambda: str(uuid4()))
    mission_id: str
    step_id: str
    policy_decision: PolicyDecision
    execution_constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)
    approval_required: bool = False
    requires_handoff: bool = False
    decision_reason: str
    confidence: float = 1.0
    risk_level: RiskLevel = "safe"
    constraints_violated: list[str] = Field(default_factory=list)
    approval_hooks: list[str] = Field(default_factory=list)
    scheduler_item_id: str | None = None
    scheduler_status: str | None = None
    replay_metadata: dict[str, Any] = Field(default_factory=dict)

    def to_stable_json(self) -> str:
        data = self.model_dump(mode="json")
        data["created_at"] = "<timestamp>"
        data["governance_id"] = "<governance_id>"
        if data.get("scheduler_item_id"):
            data["scheduler_item_id"] = "<scheduler_item_id>"
        return stable_json(data)


class ProvenanceLabel(BaseModel):
    source_type: Literal["user", "planner", "page", "tool", "system"]
    source_id: str
    trust: Literal["trusted", "untrusted"] = "untrusted"
    labels: list[str] = Field(default_factory=list)


class LivePolicyRequest(BaseModel):
    schema_version: str = "live_policy.request.v1"
    session_id: str = Field(min_length=1, max_length=200)
    origin: str = Field(min_length=1, max_length=2048)
    action: dict[str, Any]
    provenance: list[ProvenanceLabel] = Field(default_factory=list)
    origin_grant_id: str | None = None
    confirmation_receipt_id: str | None = None


class LivePolicyDecision(BaseModel):
    schema_version: str = "live_policy.decision.v1"
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    action_id: str
    action_digest: str
    origin: str
    policy_decision: PolicyDecision
    allowed: bool
    approval_required: bool
    requires_handoff: bool
    risk_level: RiskLevel
    decision_reason: str
    approval_hooks: list[str] = Field(default_factory=list)
    provenance: list[ProvenanceLabel] = Field(default_factory=list)
    receipt_id: str | None = None
    origin_grant_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OriginGrant(BaseModel):
    schema_version: str = "live_policy.origin_grant.v1"
    grant_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    origin: str
    action_types: list[str]
    issued_by: Literal["human"] = "human"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    revoked_at: datetime | None = None


class ConfirmationReceipt(BaseModel):
    schema_version: str = "live_policy.confirmation_receipt.v1"
    receipt_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    action_id: str
    action_digest: str
    origin: str
    issued_by: Literal["human"] = "human"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    consumed_at: datetime | None = None


class PolicyAuditEvent(BaseModel):
    schema_version: str = "live_policy.audit.v1"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: Literal[
        "evaluated",
        "confirmation_issued",
        "receipt_consumed",
        "origin_grant_issued",
        "origin_grant_revoked",
        "execution_allowed",
        "execution_denied",
    ]
    session_id: str
    action_id: str | None = None
    origin: str | None = None
    decision_id: str | None = None
    policy_decision: str | None = None
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
