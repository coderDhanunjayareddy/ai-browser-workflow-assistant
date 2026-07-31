from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionScoreBreakdown:
    evidence_confidence: float
    freshness: float
    contradiction_factor: float
    readiness_quality: float
    clarification_completeness: float
    provider_agreement: float
    mission_progress: float
    normalized_score: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def average(values: list[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def readiness_quality(readiness: Any | None) -> float:
    ready = len(list(getattr(readiness, "ready_nodes", []) or []))
    blocked = len(list(getattr(readiness, "blocked_nodes", []) or []))
    waiting = len(list(getattr(readiness, "waiting_nodes", []) or []))
    total = ready + blocked + waiting
    if total == 0:
        return 0.5
    return clamp((ready + 0.25 * waiting) / total)
