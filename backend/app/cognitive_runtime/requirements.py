from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.models import EvidenceCollection


@dataclass(frozen=True)
class RequirementMatch:
    requirement_id: str
    status: str
    evidence_ids: list[str]
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RequirementMatchResult:
    node_id: str
    satisfied_requirements: list[RequirementMatch]
    missing_requirements: list[RequirementMatch]
    partial_requirements: list[RequirementMatch]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "satisfied_requirements": [item.to_dict() for item in self.satisfied_requirements],
            "missing_requirements": [item.to_dict() for item in self.missing_requirements],
            "partial_requirements": [item.to_dict() for item in self.partial_requirements],
        }


class EvidenceRequirementMatcher:
    """Matches evidence to Blueprint node requirements without deciding readiness."""

    def match(self, node: Any, collection: EvidenceCollection) -> RequirementMatchResult:
        satisfied: list[RequirementMatch] = []
        missing: list[RequirementMatch] = []
        partial: list[RequirementMatch] = []
        for requirement in list(getattr(node, "evidence_requirements", []) or []):
            matches = [
                item for item in collection.evidence
                if item.evidence_type == requirement.evidence_kind
                and (
                    item.payload.get("subject") == requirement.subject
                    or item.provenance.get("blueprint_node_id") == getattr(node, "node_id", None)
                    or item.payload.get("blueprint_node_id") == getattr(node, "node_id", None)
                )
                and item.confidence >= requirement.confidence_threshold
            ]
            cardinality = int(getattr(requirement, "cardinality", 1) or 1)
            if len(matches) >= cardinality:
                satisfied.append(RequirementMatch(requirement.requirement_id, "satisfied", [item.evidence_id for item in matches]))
            elif matches:
                partial.append(
                    RequirementMatch(
                        requirement.requirement_id,
                        "partial",
                        [item.evidence_id for item in matches],
                        reason=f"requires {cardinality}, found {len(matches)}",
                    )
                )
            elif getattr(requirement, "required", True):
                missing.append(RequirementMatch(requirement.requirement_id, "missing", [], reason="no matching evidence"))
        return RequirementMatchResult(
            node_id=str(getattr(node, "node_id", "")),
            satisfied_requirements=satisfied,
            missing_requirements=missing,
            partial_requirements=partial,
        )
