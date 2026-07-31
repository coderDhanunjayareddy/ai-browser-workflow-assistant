from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CognitiveDecisionType(str, Enum):
    CONTINUE = "continue"
    WAIT = "wait"
    REQUEST_USER = "request_user"
    RECOVER = "recover"
    REPLAN = "replan"
    COMPLETE_READY = "complete_ready"
    BLOCKED = "blocked"
    FAIL = "fail"
    CANCEL = "cancel"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DecisionSignal:
    decision_type: CognitiveDecisionType
    strength: float
    reason: str
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision_type"] = self.decision_type.value
        return data


@dataclass(frozen=True)
class CognitiveDecision:
    mission_id: str
    decision_type: CognitiveDecisionType
    confidence: float
    rationale: list[str]
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    rejected_decisions: list[dict[str, Any]] = field(default_factory=list)
    policy: str = "balanced"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision_type"] = self.decision_type.value
        return data
