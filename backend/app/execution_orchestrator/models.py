from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


PhaseName = Literal[
    "DISCOVER",
    "COLLECT",
    "OPEN",
    "READ",
    "EXTRACT",
    "VALIDATE",
    "SYNTHESIZE",
    "REPORT",
    "COMPLETE",
]


@dataclass(frozen=True)
class PhaseState:
    name: PhaseName
    status: Literal["pending", "active", "complete", "blocked", "failed"] = "pending"
    objective: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    completion_reason: str | None = None
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgressLedger:
    target_counts: dict[str, int]
    current_counts: dict[str, int]
    completed: dict[str, bool]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactRegistry:
    opened_pages: list[str]
    visited_urls: list[str]
    extracted_records: list[dict[str, str]]
    screenshots: list[str]
    uploaded_files: list[str]
    downloads: list[str]
    reports: list[str]
    tables: list[str]
    summaries: list[str]
    contacts: list[dict[str, str]]
    forms: list[dict[str, str]]
    generated_files: list[str]

    def counts(self) -> dict[str, int]:
        return {
            "opened_pages": len(self.opened_pages),
            "visited_urls": len(self.visited_urls),
            "extracted_records": len(self.extracted_records),
            "screenshots": len(self.screenshots),
            "uploaded_files": len(self.uploaded_files),
            "downloads": len(self.downloads),
            "reports": len(self.reports),
            "tables": len(self.tables),
            "summaries": len(self.summaries),
            "contacts": len(self.contacts),
            "forms": len(self.forms),
            "generated_files": len(self.generated_files),
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["counts"] = self.counts()
        return data


@dataclass(frozen=True)
class ExecutionBudgets:
    max_tabs: int = 12
    max_pages: int = 30
    max_results: int = 10
    max_extractions: int = 50
    max_planner_turns: int = 40
    max_retries: int = 3
    max_tokens: int = 120000
    max_runtime_seconds: int = 900
    consumed: dict[str, int] = field(default_factory=dict)
    exhausted: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransitionRecord:
    from_phase: PhaseName
    to_phase: PhaseName
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryRoute:
    strategy: Literal["none", "retry_phase", "advance_phase", "validate_artifacts", "report_partial", "blocked"]
    phase: PhaseName
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrchestratorTelemetry:
    phase_duration_ms: int
    planner_turns_in_phase: int
    phase_retries: int
    transition_count: int
    phase_failures: int
    artifact_counts: dict[str, int]
    budget_consumption: dict[str, int]
    planner_rejection_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionOrchestratorSnapshot:
    schema_version: str
    session_id: str
    workflow_category: str
    phases: list[PhaseState]
    active_phase: PhaseState
    progress_ledger: ProgressLedger
    artifacts: ArtifactRegistry
    budgets: ExecutionBudgets
    transitions: list[TransitionRecord]
    recovery: RecoveryRoute
    replay: list[dict[str, Any]]
    telemetry: OrchestratorTelemetry

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_category": self.workflow_category,
            "active_phase": self.active_phase.to_dict(),
            "progress_ledger": self.progress_ledger.to_dict(),
            "artifact_counts": self.artifacts.counts(),
            "artifact_inputs": {
                "opened_pages": self.artifacts.opened_pages[:12],
                "visited_urls": self.artifacts.visited_urls[-12:],
                "extracted_records": self.artifacts.extracted_records[-8:],
            },
            "budgets": self.budgets.to_dict(),
            "transitions": [transition.to_dict() for transition in self.transitions[-8:]],
            "recovery": self.recovery.to_dict(),
        }
