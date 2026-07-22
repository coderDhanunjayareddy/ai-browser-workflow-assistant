from __future__ import annotations

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
