from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


class ObjectiveType(str, Enum):
    RESEARCH = "research"
    BROWSER_AUTOMATION = "browser_automation"
    ACCOUNT_CREATION = "account_creation"
    SAAS_ONBOARDING = "saas_onboarding"
    SHOPPING = "shopping"
    TRAVEL_BOOKING = "travel_booking"
    DOCUMENTATION_EXTRACTION = "documentation_extraction"
    JOB_APPLICATION = "job_application"
    FORM_WORKFLOW = "form_workflow"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    DASHBOARD = "dashboard"
    ASYNC_WORKFLOW = "async_workflow"
    GENERAL = "general"


class CriterionKind(str, Enum):
    ENTITY_COLLECTED = "entity_collected"
    ENTITY_OPENED = "entity_opened"
    PAGE_READ = "page_read"
    FIELD_EXTRACTED = "field_extracted"
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_VALIDATED = "artifact_validated"
    BROWSER_STATE_REACHED = "browser_state_reached"
    RUNTIME_BINDING_EXISTS = "runtime_binding_exists"
    FORM_COMPLETED = "form_completed"
    SUBMISSION_CONFIRMED = "submission_confirmed"
    FILE_UPLOADED = "file_uploaded"
    FILE_DOWNLOADED = "file_downloaded"
    APPROVAL_OBTAINED = "approval_obtained"
    EXTERNAL_CONFIRMATION_RECEIVED = "external_confirmation_received"
    REPORT_DELIVERED = "report_delivered"


class ValidationStatus(str, Enum):
    RAW = "raw"
    VALIDATED = "validated"
    REJECTED = "rejected"
    STALE = "stale"
    MISSING = "missing"


class CompletionDecision(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    NEEDS_USER = "NEEDS_USER"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


class CompletionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    BLOCKED = "BLOCKED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    NEEDS_USER = "NEEDS_USER"
    ABORTED = "ABORTED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    RUNNING = "RUNNING"


@dataclass(frozen=True)
class ExecutionBudgetPlan:
    max_tabs: int = 12
    max_pages: int = 30
    max_results: int = 10
    max_extractions: int = 50
    max_planner_turns: int = 40
    max_retries: int = 3
    max_tokens: int = 120000
    max_runtime_seconds: int = 900

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionSuccessCriterion:
    criterion_id: str
    kind: CriterionKind
    subject: str
    required_evidence: list[str] = field(default_factory=list)
    cardinality: int = 1
    threshold: float = 1.0
    blocking: bool = True
    optional: bool = False
    user_visible: bool = False
    freshness_seconds: int | None = None
    validation_policy: ValidationStatus = ValidationStatus.VALIDATED
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["validation_policy"] = self.validation_policy.value
        return data


@dataclass(frozen=True)
class MissionPlan:
    schema_version: str
    mission_id: str
    objective: str
    objective_type: ObjectiveType
    ordered_phases: list[str]
    constraints: list[str]
    execution_budgets: ExecutionBudgetPlan
    success_criteria: list[MissionSuccessCriterion]
    recovery_rules: list[str]
    termination_rules: list[str]
    approval_policy: dict[str, Any]

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mission_id": self.mission_id,
            "objective": self.objective,
            "objective_type": self.objective_type.value,
            "ordered_phases": self.ordered_phases,
            "success_criteria": [criterion.to_dict() for criterion in self.success_criteria],
            "termination_rules": self.termination_rules,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["objective_type"] = self.objective_type.value
        data["execution_budgets"] = self.execution_budgets.to_dict()
        data["success_criteria"] = [criterion.to_dict() for criterion in self.success_criteria]
        return data


@dataclass(frozen=True)
class EvidenceReference:
    source: str
    evidence_id: str
    evidence_type: str
    confidence: float = 1.0
    timestamp_ms: int | None = None
    validation_status: ValidationStatus = ValidationStatus.RAW

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["validation_status"] = self.validation_status.value
        return data


@dataclass(frozen=True)
class CriterionEvaluation:
    criterion_id: str
    kind: CriterionKind
    satisfied: bool
    missing_evidence: list[str]
    blocking_reason: str | None
    supporting_evidence: list[EvidenceReference]
    confidence: float
    freshness: Literal["fresh", "stale", "unknown"]
    validation_status: ValidationStatus

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["validation_status"] = self.validation_status.value
        data["supporting_evidence"] = [ref.to_dict() for ref in self.supporting_evidence]
        return data


@dataclass(frozen=True)
class SourceCoverage:
    required_count: int
    distinct_count: int
    source_urls: list[str]
    satisfied: bool
    missing_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    criteria_evaluations: list[CriterionEvaluation] = field(default_factory=list)
    source_coverage: SourceCoverage | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["criteria_evaluations"] = [evaluation.to_dict() for evaluation in self.criteria_evaluations]
        data["source_coverage"] = self.source_coverage.to_dict() if self.source_coverage else None
        return data


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
    mission_plan: MissionPlan
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
            "mission_plan": self.mission_plan.to_compact_context(),
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
        data["mission_plan"] = self.mission_plan.to_dict()
        data["decision"] = self.decision.value
        data["status"] = self.status.value
        data["evidence"] = self.evidence.to_dict()
        return data
