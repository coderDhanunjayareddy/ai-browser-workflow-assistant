from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.base import VersionedContract
from app.contracts.versions import MISSION_STATE_V1
from app.semantic_page.serializers import stable_json


MissionState = Literal[
    "created",
    "planning",
    "executing",
    "waiting",
    "replanning",
    "paused",
    "recovering",
    "completed",
    "failed",
    "cancelled",
]

MissionMode = Literal[
    "INITIALIZE",
    "PLAN",
    "ACT",
    "WAIT",
    "REPLAN",
    "PAUSE",
    "RECOVER",
    "REPORT",
    "STOP",
]


class MissionStepRef(BaseModel):
    event_id: str | None = None
    event_type: str
    step_index: int = 0
    summary: str = ""


class MissionAttempt(BaseModel):
    attempt: int
    reason: str
    event_id: str | None = None
    step_index: int = 0


class MissionSnapshot(VersionedContract):
    schema_version: str = MISSION_STATE_V1
    producer: str = "backend.mission_intelligence"
    mission_id: str
    state: MissionState = "created"
    mode: MissionMode = "INITIALIZE"
    goal: str = ""
    current_objective: str = ""
    completed_objectives: list[str] = Field(default_factory=list)
    remaining_objectives: list[str] = Field(default_factory=list)
    blocked_objectives: list[str] = Field(default_factory=list)
    progress_summary: dict[str, Any] = Field(default_factory=dict)
    step_history: list[MissionStepRef] = Field(default_factory=list)
    attempts: list[MissionAttempt] = Field(default_factory=list)
    replanning_requested: bool = False
    replan_reasons: list[str] = Field(default_factory=list)
    paused: bool = False
    planner_iterations: int = 0
    retry_count: int = 0
    recovery_count: int = 0
    completed_steps: int = 0
    elapsed_ms: int = 0
    next_expected_action: str = ""
    failure_reason: str | None = None

    def to_stable_json(self) -> str:
        data = self.model_dump(mode="json")
        data["created_at"] = "<timestamp>"
        return stable_json(data)

    @property
    def is_terminal(self) -> bool:
        return self.state in {"completed", "failed", "cancelled"}
