from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.confidence import ConfidenceEvaluator
from app.cognitive_runtime.contradiction import ContradictionDetector
from app.cognitive_runtime.freshness import FreshnessEvaluator
from app.cognitive_runtime.models import EvidenceCollection
from app.cognitive_runtime.requirements import EvidenceRequirementMatcher


@dataclass(frozen=True)
class EvidenceDiagnostics:
    mission_id: str
    evidence_count: int
    coverage: dict[str, Any]
    missing_evidence: list[dict[str, Any]]
    confidence: dict[str, Any]
    freshness: dict[str, Any]
    contradictions: list[dict[str, Any]]
    provider_distribution: dict[str, int]
    provenance_graph: dict[str, list[str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_diagnostics(
    *,
    blueprint: Any | None,
    collection: EvidenceCollection,
    requirement_matcher: EvidenceRequirementMatcher | None = None,
    confidence_evaluator: ConfidenceEvaluator | None = None,
    freshness_evaluator: FreshnessEvaluator | None = None,
    contradiction_detector: ContradictionDetector | None = None,
) -> EvidenceDiagnostics:
    requirement_matcher = requirement_matcher or EvidenceRequirementMatcher()
    confidence_evaluator = confidence_evaluator or ConfidenceEvaluator()
    freshness_evaluator = freshness_evaluator or FreshnessEvaluator()
    contradiction_detector = contradiction_detector or ContradictionDetector()
    matches = [
        requirement_matcher.match(node, collection)
        for node in list(getattr(blueprint, "nodes", []) or [])
    ]
    missing = [
        {**item.to_dict(), "node_id": match.node_id}
        for match in matches
        for item in match.missing_requirements
    ]
    total_requirements = sum(
        len(match.satisfied_requirements) + len(match.missing_requirements) + len(match.partial_requirements)
        for match in matches
    )
    satisfied_requirements = sum(len(match.satisfied_requirements) for match in matches)
    provider_distribution: dict[str, int] = {}
    provenance_graph: dict[str, list[str]] = {}
    confidence = {}
    freshness = {}
    for item in collection.evidence:
        provider_distribution[item.provider] = provider_distribution.get(item.provider, 0) + 1
        fresh = freshness_evaluator.evaluate(item)
        freshness[item.evidence_id] = fresh.to_dict()
        confidence[item.evidence_id] = confidence_evaluator.evaluate(
            item,
            freshness_factor=fresh.freshness_score,
            corroboration_count=1,
        ).to_dict()
        provenance_graph[item.evidence_id] = sorted(str(value) for value in item.provenance.values())
    coverage_ratio = satisfied_requirements / total_requirements if total_requirements else 0.0
    return EvidenceDiagnostics(
        mission_id=collection.mission_id,
        evidence_count=len(collection.evidence),
        coverage={
            "total_requirements": total_requirements,
            "satisfied_requirements": satisfied_requirements,
            "coverage_ratio": round(coverage_ratio, 4),
        },
        missing_evidence=missing,
        confidence=confidence,
        freshness=freshness,
        contradictions=[item.to_dict() for item in contradiction_detector.detect(collection)],
        provider_distribution=provider_distribution,
        provenance_graph=provenance_graph,
    )
