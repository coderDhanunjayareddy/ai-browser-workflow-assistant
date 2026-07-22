from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.versions import GROUNDING_RESULT_V1
from app.semantic_page.serializers import stable_json


GroundingStatus = Literal["resolved", "ambiguous", "not_found", "fallback", "policy_blocked"]


class GroundingCandidate(BaseModel):
    target_id: str
    target_type: str
    semantic_role: str
    label: str
    locator_candidates: list[str] = Field(default_factory=list)
    confidence: float
    match_reasons: list[str] = Field(default_factory=list)


class GroundingResult(BaseModel):
    schema_version: str = GROUNDING_RESULT_V1
    producer: str = "backend.grounding"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    run_id: str
    status: GroundingStatus
    planner_intent: str
    action_type: str
    semantic_target_id: str | None = None
    selected_selector: str | None = None
    confidence: float = 0.0
    candidates: list[GroundingCandidate] = Field(default_factory=list)
    ambiguity_reason: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    cache_hit: bool = False
    replay_metadata: dict[str, Any] = Field(default_factory=dict)

    def to_stable_json(self) -> str:
        return stable_json(self.model_dump(mode="json"))
