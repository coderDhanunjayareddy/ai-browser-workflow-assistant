from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.contracts.versions import PLANNER_PACKET_V1
from app.semantic_page.serializers import stable_json


class ContextBudgetMetadata(BaseModel):
    max_entities: int
    max_targets: int
    max_facts: int
    max_controls: int
    max_packet_chars: int
    original_counts: dict[str, int] = Field(default_factory=dict)
    trimmed_counts: dict[str, int] = Field(default_factory=dict)
    packet_chars: int = 0


class PlannerPacket(BaseModel):
    schema_version: str = PLANNER_PACKET_V1
    run: dict[str, Any] = Field(default_factory=dict)
    mission_context: dict[str, Any] = Field(default_factory=dict)
    task_context: dict[str, Any] = Field(default_factory=dict)
    browser_context: dict[str, Any] = Field(default_factory=dict)
    page_context: dict[str, Any] = Field(default_factory=dict)
    memory_context: dict[str, Any] = Field(default_factory=dict)
    policy_context: dict[str, Any] = Field(default_factory=dict)
    capability_context: dict[str, Any] = Field(default_factory=dict)
    recovery_context: dict[str, Any] = Field(default_factory=dict)
    validation_context: dict[str, Any] = Field(default_factory=dict)
    output_contract: str = "planner_contract_v2"
    budget_metadata: ContextBudgetMetadata

    def to_stable_json(self) -> str:
        return stable_json(self.model_dump(mode="json"))
