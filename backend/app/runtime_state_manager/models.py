from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class RuntimeTab:
    logical_id: str
    runtime_id: str | None
    window_id: str
    url: str
    title: str
    page_type: str
    opener_logical_id: str | None
    lifecycle: Literal["active", "opened", "navigated", "closed", "unknown"]
    active: bool
    focus_index: int
    navigation_history: list[str]
    created_at_ms: int
    updated_at_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeWindow:
    logical_id: str
    runtime_id: str | None
    active: bool
    tab_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LogicalResource:
    logical_id: str
    resource_type: Literal["tab", "window", "download", "upload", "form", "document", "page", "artifact"]
    runtime_id: str | None
    current_url: str | None
    mission_entity_id: str | None
    page_type: str | None
    status: Literal["active", "available", "missing", "completed", "failed", "unknown"]
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeArtifact:
    logical_id: str
    artifact_type: str
    owner_phase: str
    producing_action: str
    producing_page: str | None
    validation_status: Literal["unknown", "valid", "invalid", "pending"]
    completion_status: Literal["pending", "complete", "failed"]
    payload: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeCheckpoint:
    checkpoint_id: str
    current_phase: str | None
    opened_tabs: list[str]
    visited_pages: list[str]
    artifacts: list[str]
    extraction_progress: dict[str, int]
    completed_entities: list[str]
    budgets: dict[str, int]
    recovery_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeConsistencyResult:
    valid: bool
    violations: list[str]
    repairable: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeRecoveryEvent:
    strategy: Literal["none", "recover_runtime_id", "focus_by_url", "restore_checkpoint", "notify_orchestrator"]
    reason: str
    recovered: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeTelemetry:
    registry_lookup_ms: int
    synchronization_ms: int
    tab_count: int
    window_count: int
    artifact_count: int
    registry_repairs: int
    recovery_events: int
    consistency_violations: int
    checkpoint_restores: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeStateSnapshot:
    schema_version: str
    session_id: str
    windows: list[RuntimeWindow]
    tabs: list[RuntimeTab]
    focused_tab_id: str | None
    logical_resources: list[LogicalResource]
    artifacts: list[RuntimeArtifact]
    checkpoint: RuntimeCheckpoint
    consistency: RuntimeConsistencyResult
    recovery: RuntimeRecoveryEvent
    telemetry: RuntimeTelemetry
    replay: list[dict[str, Any]]

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "focused_tab_id": self.focused_tab_id,
            "tabs": [tab.to_dict() for tab in self.tabs[-12:]],
            "logical_resources": [resource.to_dict() for resource in self.logical_resources[-20:]],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts[-16:]],
            "checkpoint": self.checkpoint.to_dict(),
            "consistency": self.consistency.to_dict(),
            "recovery": self.recovery.to_dict(),
        }
