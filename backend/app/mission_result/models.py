from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MissionOutcome = Literal["COMPLETE", "PARTIAL_SUCCESS", "FAILED", "INCOMPLETE", "BLOCKED"]
ArtifactKind = Literal["markdown_report", "comparison_table", "structured_json", "download"]


class MissionResultArtifact(BaseModel):
    artifact_id: str
    mission_result_id: str
    mission_id: str
    kind: ArtifactKind
    title: str
    content_type: str
    content: str
    structured: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MissionResultArtifactSummary(BaseModel):
    artifact_id: str
    mission_result_id: str
    mission_id: str
    kind: ArtifactKind
    title: str
    content_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MissionResult(BaseModel):
    mission_result_id: str
    mission_id: str
    outcome: MissionOutcome
    final_answer: str
    report_format: str
    report_artifact_id: str | None = None
    knowledge_artifact_id: str | None = None
    completion_reason: str
    confidence: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[MissionResultArtifact] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MissionResultSummary(BaseModel):
    mission_result_id: str
    mission_id: str
    outcome: MissionOutcome
    report_artifact_id: str | None = None
    knowledge_artifact_id: str | None = None
    completion_reason: str
    confidence: float
    artifact_count: int
    created_at: datetime
    updated_at: datetime


class MissionResultVersion(BaseModel):
    version_id: str
    mission_result_id: str
    mission_id: str
    version: int
    reason: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
