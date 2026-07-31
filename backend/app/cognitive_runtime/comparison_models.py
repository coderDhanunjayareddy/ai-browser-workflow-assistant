from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class RuntimeDecisionType(str, Enum):
    CONTINUE = "CONTINUE"
    WAIT = "WAIT"
    REQUEST_USER = "REQUEST_USER"
    RECOVER = "RECOVER"
    REPLAN = "REPLAN"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class AgreementType(str, Enum):
    EXACT = "exact"
    SEMANTIC = "semantic"
    PARTIAL = "partial"
    DISAGREEMENT = "disagreement"


@dataclass(frozen=True)
class DecisionComparison:
    mission_id: str
    runtime_decision: str
    cognitive_decision: str
    agreement: str
    confidence: float
    runtime_reason: str
    cognitive_reason: str
    explanation: dict[str, Any]
    intent_id: str | None = None
    blueprint_node_id: str | None = None
    comparison_id: str = field(default_factory=lambda: f"decision_cmp_{uuid.uuid4().hex}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DecisionComparison":
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now(UTC)
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(UTC)
        return cls(
            comparison_id=str(data.get("comparison_id") or f"decision_cmp_{uuid.uuid4().hex}"),
            mission_id=str(data.get("mission_id") or ""),
            intent_id=data.get("intent_id"),
            blueprint_node_id=data.get("blueprint_node_id"),
            runtime_decision=str(data.get("runtime_decision") or RuntimeDecisionType.UNKNOWN.value),
            cognitive_decision=str(data.get("cognitive_decision") or "unknown"),
            agreement=str(data.get("agreement") or AgreementType.DISAGREEMENT.value),
            confidence=float(data.get("confidence") or 0.0),
            runtime_reason=str(data.get("runtime_reason") or ""),
            cognitive_reason=str(data.get("cognitive_reason") or ""),
            explanation=dict(data.get("explanation") or {}),
            timestamp=timestamp,
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(frozen=True)
class AgreementResult:
    agreement: AgreementType
    runtime_decision: str
    cognitive_decision: str
    disagreement_type: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["agreement"] = self.agreement.value
        return data
