from __future__ import annotations

from dataclasses import asdict, dataclass

from app.cognitive_runtime.models import CognitiveEvidence


@dataclass(frozen=True)
class ConfidenceScore:
    evidence_id: str
    normalized_confidence: float
    provider_confidence: float
    freshness_factor: float
    corroboration_factor: float
    provenance_factor: float

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


class ConfidenceEvaluator:
    """Normalizes evidence confidence without making completion decisions."""

    def evaluate(
        self,
        evidence: CognitiveEvidence,
        *,
        freshness_factor: float = 1.0,
        corroboration_count: int = 1,
    ) -> ConfidenceScore:
        provider_confidence = _clamp(evidence.confidence)
        freshness = _clamp(freshness_factor)
        corroboration = _clamp(0.7 + min(max(corroboration_count - 1, 0), 3) * 0.1)
        provenance = _provenance_quality(evidence)
        normalized = _clamp(
            provider_confidence * 0.45
            + freshness * 0.2
            + corroboration * 0.2
            + provenance * 0.15
        )
        return ConfidenceScore(
            evidence_id=evidence.evidence_id,
            normalized_confidence=round(normalized, 4),
            provider_confidence=provider_confidence,
            freshness_factor=freshness,
            corroboration_factor=corroboration,
            provenance_factor=provenance,
        )


def _provenance_quality(evidence: CognitiveEvidence) -> float:
    if not evidence.provenance:
        return 0.4
    keys = set(evidence.provenance)
    score = 0.4
    if keys & {"intent_id", "ledger_intent_id"}:
        score += 0.25
    if keys & {"blueprint_node_id", "blueprint_id"}:
        score += 0.2
    if keys & {"provider_event_id", "source_url", "artifact_id"}:
        score += 0.15
    return _clamp(score)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
