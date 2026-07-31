from __future__ import annotations

from typing import Any

from app.cognitive_runtime.decision_scores import DecisionScoreBreakdown, average, clamp, readiness_quality
from app.cognitive_runtime.models import EvidenceCollection


class DecisionConfidenceEngine:
    """Computes advisory confidence for a cognitive decision."""

    def score(
        self,
        *,
        evidence: EvidenceCollection,
        diagnostics: Any | None,
        readiness: Any | None,
        clarification: Any | None,
        progress: Any | None,
    ) -> DecisionScoreBreakdown:
        evidence_confidence = average([item.confidence for item in evidence.evidence], default=0.5)
        freshness_values = [
            float(item.get("freshness_score", 1.0))
            for item in dict(getattr(diagnostics, "freshness", {}) or {}).values()
            if isinstance(item, dict)
        ]
        freshness = average(freshness_values, default=1.0)
        contradictions = len(list(getattr(diagnostics, "contradictions", []) or []))
        contradiction_factor = clamp(1.0 - min(contradictions, 5) * 0.2)
        readiness = readiness_quality(readiness)
        unanswered = int(getattr(clarification, "unanswered_count", 0) or 0)
        clarification_completeness = clamp(1.0 - min(unanswered, 5) * 0.2)
        providers = {item.provider for item in evidence.evidence}
        provider_agreement = 1.0 if len(providers) <= 1 else clamp(0.7 + min(len(providers), 3) * 0.1)
        mission_progress = clamp(float(getattr(progress, "completion_percentage", 0.0) or 0.0))
        normalized = (
            evidence_confidence * 0.25
            + freshness * 0.15
            + contradiction_factor * 0.15
            + readiness * 0.15
            + clarification_completeness * 0.1
            + provider_agreement * 0.1
            + mission_progress * 0.1
        )
        return DecisionScoreBreakdown(
            evidence_confidence=round(evidence_confidence, 4),
            freshness=round(freshness, 4),
            contradiction_factor=round(contradiction_factor, 4),
            readiness_quality=round(readiness, 4),
            clarification_completeness=round(clarification_completeness, 4),
            provider_agreement=round(provider_agreement, 4),
            mission_progress=round(mission_progress, 4),
            normalized_score=round(clamp(normalized), 4),
        )
