from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.cognitive_runtime.versioning import RuntimeVersion


class CognitiveValidationError(ValueError):
    """Raised when a Cognitive Runtime V2 object violates its passive contract."""


class CognitiveState(str, Enum):
    INITIALIZED = "initialized"
    UNDERSTANDING = "understanding"
    READY = "ready"
    EXECUTING = "executing"
    WAITING_BROWSER = "waiting_browser"
    WAITING_USER = "waiting_user"
    WAITING_EXTERNAL = "waiting_external"
    BLOCKED = "blocked"
    REPLANNING = "replanning"
    RECOVERING = "recovering"
    PARTIAL_SUCCESS = "partial_success"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class CognitiveMission:
    mission_id: str
    blueprint_id: str
    blueprint_revision: int
    runtime_version: RuntimeVersion = field(default_factory=RuntimeVersion)
    state: CognitiveState = CognitiveState.INITIALIZED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.mission_id.strip():
            raise CognitiveValidationError("mission_id is required")
        if not self.blueprint_id.strip():
            raise CognitiveValidationError("blueprint_id is required")
        if self.blueprint_revision < 1:
            raise CognitiveValidationError("blueprint_revision must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        data = _jsonable(asdict(self))
        data["state"] = self.state.value
        data["runtime_version"] = self.runtime_version.to_dict()
        return data

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CognitiveMission:
        return cls(
            mission_id=str(payload.get("mission_id") or ""),
            blueprint_id=str(payload.get("blueprint_id") or ""),
            blueprint_revision=int(payload.get("blueprint_revision") or 1),
            runtime_version=RuntimeVersion.from_dict(payload.get("runtime_version")),
            state=CognitiveState(str(payload.get("state") or CognitiveState.INITIALIZED.value)),
            created_at=_datetime(payload.get("created_at")),
            updated_at=_datetime(payload.get("updated_at")),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class CognitiveEvidence:
    evidence_id: str
    mission_id: str
    source: str
    provider: str
    evidence_type: str
    payload: dict[str, Any]
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise CognitiveValidationError("evidence_id is required")
        if not self.mission_id.strip():
            raise CognitiveValidationError("mission_id is required")
        if not self.source.strip():
            raise CognitiveValidationError("source is required")
        if not self.provider.strip():
            raise CognitiveValidationError("provider is required")
        if not self.evidence_type.strip():
            raise CognitiveValidationError("evidence_type is required")
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise CognitiveValidationError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CognitiveEvidence:
        return cls(
            evidence_id=str(payload.get("evidence_id") or ""),
            mission_id=str(payload.get("mission_id") or ""),
            source=str(payload.get("source") or ""),
            provider=str(payload.get("provider") or ""),
            evidence_type=str(payload.get("evidence_type") or ""),
            payload=dict(payload.get("payload") or {}),
            confidence=float(payload.get("confidence", 1.0)),
            timestamp=_datetime(payload.get("timestamp")),
            provenance=dict(payload.get("provenance") or {}),
        )


@dataclass(frozen=True)
class EvidenceCollection:
    mission_id: str
    evidence: tuple[CognitiveEvidence, ...] = field(default_factory=tuple)

    def merge(self, other: EvidenceCollection | list[CognitiveEvidence]) -> EvidenceCollection:
        incoming = other.evidence if isinstance(other, EvidenceCollection) else tuple(other)
        return EvidenceCollection(self.mission_id, tuple(_dedupe([*self.evidence, *incoming])))

    def deduplicate(self) -> EvidenceCollection:
        return EvidenceCollection(self.mission_id, tuple(_dedupe(self.evidence)))

    def provenance_lookup(self, key: str, value: Any) -> list[CognitiveEvidence]:
        return [item for item in self.evidence if item.provenance.get(key) == value]

    def to_dict(self) -> dict[str, Any]:
        return {"mission_id": self.mission_id, "evidence": [item.to_dict() for item in self.evidence]}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidenceCollection:
        return cls(
            mission_id=str(payload.get("mission_id") or ""),
            evidence=tuple(CognitiveEvidence.from_dict(item) for item in list(payload.get("evidence") or [])),
        )


@dataclass(frozen=True)
class ProgressSnapshot:
    mission_id: str
    blueprint_id: str
    blueprint_revision: int
    completed_nodes: list[str] = field(default_factory=list)
    ready_nodes: list[str] = field(default_factory=list)
    blocked_nodes: list[str] = field(default_factory=list)
    waiting_nodes: list[str] = field(default_factory=list)
    evidence_coverage: float = 0.0
    completion_percentage: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProgressSnapshot:
        return cls(
            mission_id=str(payload.get("mission_id") or ""),
            blueprint_id=str(payload.get("blueprint_id") or ""),
            blueprint_revision=int(payload.get("blueprint_revision") or 1),
            completed_nodes=list(payload.get("completed_nodes") or []),
            ready_nodes=list(payload.get("ready_nodes") or []),
            blocked_nodes=list(payload.get("blocked_nodes") or []),
            waiting_nodes=list(payload.get("waiting_nodes") or []),
            evidence_coverage=float(payload.get("evidence_coverage") or 0.0),
            completion_percentage=float(payload.get("completion_percentage") or 0.0),
            metadata=dict(payload.get("metadata") or {}),
            created_at=_datetime(payload.get("created_at")),
        )


@dataclass(frozen=True)
class CognitiveCheckpoint:
    checkpoint_id: str
    mission_id: str
    blueprint_revision: int
    serialized_state: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, *, mission_id: str, blueprint_revision: int, serialized_state: dict[str, Any]) -> CognitiveCheckpoint:
        return cls(
            checkpoint_id=f"cognitive_checkpoint_{uuid.uuid4().hex}",
            mission_id=mission_id,
            blueprint_revision=blueprint_revision,
            serialized_state=dict(serialized_state),
        )

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CognitiveCheckpoint:
        return cls(
            checkpoint_id=str(payload.get("checkpoint_id") or ""),
            mission_id=str(payload.get("mission_id") or ""),
            blueprint_revision=int(payload.get("blueprint_revision") or 1),
            serialized_state=dict(payload.get("serialized_state") or {}),
            timestamp=_datetime(payload.get("timestamp")),
        )


@dataclass(frozen=True)
class CognitiveMetrics:
    mission_id: str
    reasoning_iterations: int = 0
    clarification_count: int = 0
    evidence_count: int = 0
    confidence_average: float = 0.0
    recovery_count: int = 0
    replanning_count: int = 0
    execution_duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CognitiveMetrics:
        return cls(
            mission_id=str(payload.get("mission_id") or ""),
            reasoning_iterations=int(payload.get("reasoning_iterations") or 0),
            clarification_count=int(payload.get("clarification_count") or 0),
            evidence_count=int(payload.get("evidence_count") or 0),
            confidence_average=float(payload.get("confidence_average") or 0.0),
            recovery_count=int(payload.get("recovery_count") or 0),
            replanning_count=int(payload.get("replanning_count") or 0),
            execution_duration_ms=int(payload.get("execution_duration_ms") or 0),
            metadata=dict(payload.get("metadata") or {}),
            updated_at=_datetime(payload.get("updated_at")),
        )


def _dedupe(items: list[CognitiveEvidence] | tuple[CognitiveEvidence, ...]) -> list[CognitiveEvidence]:
    seen: set[str] = set()
    deduped: list[CognitiveEvidence] = []
    for item in items:
        if item.evidence_id in seen:
            continue
        seen.add(item.evidence_id)
        deduped.append(item)
    return deduped


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return datetime.now(UTC)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
