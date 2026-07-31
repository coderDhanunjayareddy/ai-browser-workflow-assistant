from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.cognitive_runtime.models import CognitiveEvidence


@dataclass(frozen=True)
class FreshnessReport:
    evidence_id: str
    age_seconds: float
    freshness_score: float
    stale: bool
    expiration_seconds: int | None

    def to_dict(self) -> dict[str, float | bool | int | str | None]:
        return asdict(self)


class FreshnessEvaluator:
    """Evaluates evidence age and staleness without mutating mission state."""

    def evaluate(
        self,
        evidence: CognitiveEvidence,
        *,
        now: datetime | None = None,
        default_expiration_seconds: int | None = None,
    ) -> FreshnessReport:
        now = now or datetime.now(UTC)
        timestamp = evidence.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        expiration = _expiration(evidence, default_expiration_seconds)
        age = max(0.0, (now - timestamp).total_seconds())
        if expiration is None:
            score = 1.0
            stale = False
        else:
            score = max(0.0, 1.0 - (age / max(expiration, 1)))
            stale = age > expiration
        return FreshnessReport(
            evidence_id=evidence.evidence_id,
            age_seconds=round(age, 4),
            freshness_score=round(score, 4),
            stale=stale,
            expiration_seconds=expiration,
        )


def _expiration(evidence: CognitiveEvidence, default: int | None) -> int | None:
    value = evidence.provenance.get("expiration_seconds", evidence.payload.get("expiration_seconds", default))
    return int(value) if value is not None else None
