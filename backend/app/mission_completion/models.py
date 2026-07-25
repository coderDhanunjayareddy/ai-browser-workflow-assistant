from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


class CompletionDecision(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    RETRY = "RETRY"
    CONTINUE = "CONTINUE"


class CompletionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    RUNNING = "RUNNING"


@dataclass(frozen=True)
class CompletionEvidence:
    required_fields: list[str]
    read_count: int
    extraction_record_count: int
    valid_record_count: int
    report_artifact_id: str | None
    knowledge_artifact_id: str | None
    missing_artifacts: list[str]
    completion_status: dict[str, bool]
    source_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompletionTelemetry:
    completion_latency_ms: int
    completion_reason: str
    completion_status: str
    planner_calls_saved: int
    completion_confidence: float
    partial_completion_count: int
    retry_decisions: int
    report_generation_ms: int
    workflow_exit_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkflowResult:
    mission_status: str
    completion_reason: str
    report_artifact: dict[str, Any] | None
    replay_reference: str | None
    metrics: dict[str, Any]
    evidence_summary: dict[str, Any]
    duration_ms: int
    resource_usage: dict[str, Any]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionCompletionSnapshot:
    schema_version: str
    session_id: str
    decision: CompletionDecision
    status: CompletionStatus
    reason: str
    confidence: float
    evidence: CompletionEvidence
    workflow_result: WorkflowResult | None
    telemetry: CompletionTelemetry
    replay: list[dict[str, Any]] = field(default_factory=list)
    retry_target: Literal["read", "extract", "validate", "synthesize", "report", "recovery", "none"] = "none"

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision.value,
            "status": self.status.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "retry_target": self.retry_target,
            "evidence": self.evidence.to_dict(),
            "workflow_result_exists": self.workflow_result is not None,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        data["status"] = self.status.value
        return data
