from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.contradiction import ContradictionDetector
from app.cognitive_runtime.diagnostics import EvidenceDiagnostics, build_diagnostics
from app.cognitive_runtime.fusion import EvidenceFusionEngine, FusedEvidenceResult
from app.cognitive_runtime.models import CognitiveEvidence, EvidenceCollection
from app.cognitive_runtime.requirements import EvidenceRequirementMatcher, RequirementMatchResult


@dataclass(frozen=True)
class EvidenceInterpretation:
    mission_id: str
    fused: dict[str, Any]
    requirement_matches: list[dict[str, Any]]
    duplicate_evidence: int
    contradictions: list[dict[str, Any]]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvidenceInterpreter:
    """Pure reasoning engine for Cognitive Runtime evidence."""

    def __init__(
        self,
        *,
        fusion_engine: EvidenceFusionEngine | None = None,
        requirement_matcher: EvidenceRequirementMatcher | None = None,
        contradiction_detector: ContradictionDetector | None = None,
    ):
        self.fusion_engine = fusion_engine or EvidenceFusionEngine()
        self.requirement_matcher = requirement_matcher or EvidenceRequirementMatcher()
        self.contradiction_detector = contradiction_detector or ContradictionDetector()

    def normalize(self, evidence: CognitiveEvidence) -> CognitiveEvidence:
        return CognitiveEvidence(
            evidence_id=evidence.evidence_id,
            mission_id=evidence.mission_id,
            source=evidence.source.strip().lower(),
            provider=evidence.provider.strip().lower(),
            evidence_type=evidence.evidence_type.strip().lower(),
            payload=dict(evidence.payload),
            confidence=max(0.0, min(1.0, evidence.confidence)),
            timestamp=evidence.timestamp,
            provenance=dict(evidence.provenance),
        )

    def classify(self, evidence: CognitiveEvidence) -> str:
        if evidence.evidence_type.startswith("validation"):
            return "validation"
        if evidence.evidence_type in {"field_extraction", "node_satisfied", "blueprint_node_satisfied"}:
            return "semantic"
        if evidence.provider in {"browser", "browser_control"}:
            return "browser"
        return "general"

    def interpret(self, *, blueprint: Any | None, collection: EvidenceCollection) -> EvidenceInterpretation:
        normalized = EvidenceCollection(
            mission_id=collection.mission_id,
            evidence=tuple(self.normalize(item) for item in collection.evidence),
        )
        fused: FusedEvidenceResult = self.fusion_engine.fuse([normalized])
        requirement_matches: list[RequirementMatchResult] = [
            self.requirement_matcher.match(node, fused.collection)
            for node in list(getattr(blueprint, "nodes", []) or [])
        ]
        contradictions = self.contradiction_detector.detect(fused.collection)
        diagnostics: EvidenceDiagnostics = build_diagnostics(blueprint=blueprint, collection=fused.collection)
        return EvidenceInterpretation(
            mission_id=collection.mission_id,
            fused=fused.to_dict(),
            requirement_matches=[item.to_dict() for item in requirement_matches],
            duplicate_evidence=fused.duplicates_collapsed,
            contradictions=[item.to_dict() for item in contradictions],
            diagnostics=diagnostics.to_dict(),
        )
