from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.models import EvidenceCollection


@dataclass(frozen=True)
class ClarificationDiagnostics:
    required_count: int
    optional_count: int
    unanswered_count: int
    urgency: str
    groups: dict[str, list[dict[str, Any]]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ClarificationEngine:
    """Detects unanswered Blueprint clarification requirements without asking users."""

    def evaluate(self, *, blueprint: Any | None, evidence: EvidenceCollection) -> ClarificationDiagnostics:
        requirements = [
            requirement
            for node in list(getattr(blueprint, "nodes", []) or [])
            for requirement in list(getattr(node, "clarification_requirements", []) or [])
        ]
        answered = {
            item.payload.get("clarification_id") or item.provenance.get("clarification_id") or item.payload.get("subject")
            for item in evidence.evidence
            if item.evidence_type == "clarification_obtained"
        }
        unanswered = [item for item in requirements if item.clarification_id not in answered]
        required = [item for item in unanswered if item.required]
        optional = [item for item in unanswered if not item.required]
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in unanswered:
            group = "blocking" if item.required else "optional"
            groups.setdefault(group, []).append({
                "clarification_id": item.clarification_id,
                "question": item.question,
                "blocks_node_ids": list(item.blocks_node_ids),
            })
        urgency = "none"
        if required:
            urgency = "high"
        elif optional:
            urgency = "low"
        return ClarificationDiagnostics(
            required_count=len(required),
            optional_count=len(optional),
            unanswered_count=len(unanswered),
            urgency=urgency,
            groups=groups,
        )
