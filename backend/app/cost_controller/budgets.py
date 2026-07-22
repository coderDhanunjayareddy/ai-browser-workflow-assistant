from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.contracts.base import VersionedContract
from app.contracts.versions import COST_BUDGET_V1, COST_DECISION_V1


class CostBudget(VersionedContract):
    schema_version: str = COST_BUDGET_V1
    producer: str = "backend.cost_controller"
    max_tokens: int = 50000
    max_vision_calls: int = 0
    max_provider_cost: float = 0.0
    max_latency_ms: int = 60000
    max_workflow_duration_ms: int = 300000


class CostUsage(BaseModel):
    tokens: int = 0
    vision_calls: int = 0
    provider_cost: float = 0.0
    latency_ms: int = 0
    workflow_duration_ms: int = 0


class CostDecision(VersionedContract):
    schema_version: str = COST_DECISION_V1
    producer: str = "backend.cost_controller"
    status: Literal["within_budget", "near_limit", "exceeded"]
    reason: str
    planner_guidance: str = ""
    hard_stop: bool = False
