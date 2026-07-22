from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.contracts.base import VersionedContract
from app.contracts.versions import (
    EVALUATION_OBJECT_V1,
    KNOWLEDGE_RECORD_V1,
    LEARNING_SIGNAL_V1,
    RUN_SCORECARD_V1,
)
from app.semantic_page.serializers import stable_json


EvaluationStatus = Literal["succeeded", "failed", "partial", "unknown"]
LearningSignalKind = Literal[
    "successful_grounding_pattern",
    "repeated_failure",
    "common_recovery_path",
    "frequent_ambiguity",
    "validation_failure",
    "policy_warning",
    "mission_success",
]


class EvaluationScoreDimensions(BaseModel):
    mission_success: float = 0.0
    validation_success: float = 0.0
    grounding_quality: float = 0.0
    retry_efficiency: float = 0.0
    execution_efficiency: float = 0.0
    governance_compliance: float = 0.0
    replay_quality: float = 0.0

    def overall(self) -> float:
        values = [
            self.mission_success,
            self.validation_success,
            self.grounding_quality,
            self.retry_efficiency,
            self.execution_efficiency,
            self.governance_compliance,
            self.replay_quality,
        ]
        return round(sum(values) / len(values), 4)


class ExecutionMetrics(BaseModel):
    planner_turns: int = 0
    browser_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    retry_count: int = 0
    recovery_count: int = 0
    total_latency_ms: int = 0
    first_event_type: str | None = None
    final_event_type: str | None = None


class EvaluationObject(VersionedContract):
    schema_version: str = EVALUATION_OBJECT_V1
    producer: str = "backend.evaluation"
    evaluation_id: str = Field(default_factory=lambda: str(uuid4()))
    mission_id: str
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    governance_summary: dict[str, Any] = Field(default_factory=dict)
    mission_summary: dict[str, Any] = Field(default_factory=dict)
    execution_metrics: ExecutionMetrics = Field(default_factory=ExecutionMetrics)
    score_dimensions: EvaluationScoreDimensions = Field(default_factory=EvaluationScoreDimensions)
    overall_score: float = 0.0
    confidence: float = 0.0
    timestamp: str
    replay_metadata: dict[str, Any] = Field(default_factory=dict)

    def to_stable_json(self) -> str:
        data = self.model_dump(mode="json")
        data["created_at"] = "<timestamp>"
        data["timestamp"] = "<timestamp>"
        data["evaluation_id"] = "<evaluation_id>"
        if isinstance(data.get("replay_metadata"), dict):
            data["replay_metadata"]["first_event_id"] = "<event_id>"
            data["replay_metadata"]["last_event_id"] = "<event_id>"
        return stable_json(data)


class LearningSignal(VersionedContract):
    schema_version: str = LEARNING_SIGNAL_V1
    producer: str = "backend.evaluation"
    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    evaluation_id: str
    mission_id: str
    kind: LearningSignalKind
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_stable_json(self) -> str:
        data = self.model_dump(mode="json")
        data["created_at"] = "<timestamp>"
        data["signal_id"] = "<signal_id>"
        data["evaluation_id"] = "<evaluation_id>"
        return stable_json(data)


class KnowledgeRecord(VersionedContract):
    schema_version: str = KNOWLEDGE_RECORD_V1
    producer: str = "backend.evaluation"
    record_id: str = Field(default_factory=lambda: str(uuid4()))
    evaluation_id: str
    mission_id: str
    category: str
    summary: str
    facts: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    provenance: list[str] = Field(default_factory=list)

    def to_stable_json(self) -> str:
        data = self.model_dump(mode="json")
        data["created_at"] = "<timestamp>"
        data["record_id"] = "<record_id>"
        data["evaluation_id"] = "<evaluation_id>"
        return stable_json(data)


class RunScorecard(VersionedContract):
    schema_version: str = RUN_SCORECARD_V1
    producer: str = "backend.evaluation"
    scorecard_id: str = Field(default_factory=lambda: str(uuid4()))
    evaluation_id: str
    mission_id: str
    status: EvaluationStatus = "unknown"
    success: bool = False
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    governance_summary: dict[str, Any] = Field(default_factory=dict)
    timing: dict[str, Any] = Field(default_factory=dict)
    retries: int = 0
    confidence: float = 0.0
    overall_score: float = 0.0
    regression_flags: list[str] = Field(default_factory=list)

    def to_stable_json(self) -> str:
        data = self.model_dump(mode="json")
        data["created_at"] = "<timestamp>"
        data["scorecard_id"] = "<scorecard_id>"
        data["evaluation_id"] = "<evaluation_id>"
        return stable_json(data)


class EvaluationArtifacts(BaseModel):
    evaluation: EvaluationObject
    scorecard: RunScorecard
    learning_signals: list[LearningSignal] = Field(default_factory=list)
    knowledge_records: list[KnowledgeRecord] = Field(default_factory=list)
    latency_ms: int = 0
