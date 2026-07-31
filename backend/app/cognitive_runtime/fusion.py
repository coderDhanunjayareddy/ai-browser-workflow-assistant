from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.cognitive_runtime.confidence import ConfidenceEvaluator
from app.cognitive_runtime.freshness import FreshnessEvaluator
from app.cognitive_runtime.models import CognitiveEvidence, EvidenceCollection


@dataclass(frozen=True)
class FusedEvidenceResult:
    collection: EvidenceCollection
    duplicates_collapsed: int
    provider_distribution: dict[str, int]
    confidence_by_evidence: dict[str, float]
    provenance_graph: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["collection"] = self.collection.to_dict()
        return data


class EvidenceFusionEngine:
    """Merges provider evidence while preserving provenance and collapsing duplicates."""

    def __init__(
        self,
        *,
        confidence_evaluator: ConfidenceEvaluator | None = None,
        freshness_evaluator: FreshnessEvaluator | None = None,
        provider_weights: dict[str, float] | None = None,
    ):
        self.confidence_evaluator = confidence_evaluator or ConfidenceEvaluator()
        self.freshness_evaluator = freshness_evaluator or FreshnessEvaluator()
        self.provider_weights = dict(provider_weights or {})

    def fuse(self, collections: list[EvidenceCollection]) -> FusedEvidenceResult:
        if not collections:
            return FusedEvidenceResult(EvidenceCollection(mission_id=""), 0, {}, {})
        mission_id = collections[0].mission_id
        items = [item for collection in collections for item in collection.evidence]
        fused: dict[tuple[str, str, str], CognitiveEvidence] = {}
        duplicates = 0
        for item in items:
            key = _dedupe_key(item)
            if key in fused:
                duplicates += 1
                fused[key] = _prefer(fused[key], item)
            else:
                fused[key] = item
        evidence = list(fused.values())
        provider_distribution: dict[str, int] = {}
        confidence: dict[str, float] = {}
        provenance_graph: dict[str, list[str]] = {}
        for item in evidence:
            provider_distribution[item.provider] = provider_distribution.get(item.provider, 0) + 1
            freshness = self.freshness_evaluator.evaluate(item).freshness_score
            score = self.confidence_evaluator.evaluate(
                item,
                freshness_factor=freshness,
                corroboration_count=_corroboration_count(items, item),
            ).normalized_confidence
            confidence[item.evidence_id] = round(score * self.provider_weights.get(item.provider, 1.0), 4)
            provenance_graph[item.evidence_id] = sorted(str(value) for value in item.provenance.values())
        return FusedEvidenceResult(
            collection=EvidenceCollection(mission_id=mission_id, evidence=tuple(evidence)),
            duplicates_collapsed=duplicates,
            provider_distribution=provider_distribution,
            confidence_by_evidence=confidence,
            provenance_graph=provenance_graph,
        )


def _dedupe_key(evidence: CognitiveEvidence) -> tuple[str, str, str]:
    subject = str(evidence.provenance.get("blueprint_node_id") or evidence.payload.get("subject") or evidence.evidence_id)
    fingerprint = str(evidence.payload.get("fingerprint") or evidence.payload.get("value") or evidence.payload)
    return subject, evidence.evidence_type, fingerprint


def _prefer(left: CognitiveEvidence, right: CognitiveEvidence) -> CognitiveEvidence:
    return right if right.confidence > left.confidence else left


def _corroboration_count(items: list[CognitiveEvidence], evidence: CognitiveEvidence) -> int:
    subject = str(evidence.provenance.get("blueprint_node_id") or evidence.payload.get("subject") or evidence.evidence_id)
    return sum(
        1 for item in items
        if item.evidence_type == evidence.evidence_type
        and str(item.provenance.get("blueprint_node_id") or item.payload.get("subject") or item.evidence_id) == subject
    )
