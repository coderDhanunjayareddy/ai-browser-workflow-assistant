from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.models import CognitiveEvidence, EvidenceCollection


@dataclass(frozen=True)
class ContradictionReport:
    subject: str
    field: str
    values: dict[str, list[str]]
    evidence_ids: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContradictionDetector:
    """Detects incompatible evidence claims. It reports conflicts but never resolves them."""

    def detect(self, collection: EvidenceCollection) -> list[ContradictionReport]:
        buckets: dict[tuple[str, str], dict[str, list[str]]] = {}
        evidence_ids: dict[tuple[str, str], list[str]] = {}
        for item in collection.evidence:
            subject = _subject(item)
            for field, value in _claims(item).items():
                if value is None or isinstance(value, (dict, list)):
                    continue
                key = (subject, field)
                buckets.setdefault(key, {}).setdefault(str(value), []).append(item.evidence_id)
                evidence_ids.setdefault(key, []).append(item.evidence_id)
        reports: list[ContradictionReport] = []
        for (subject, field), values in buckets.items():
            if len(values) <= 1:
                continue
            reports.append(
                ContradictionReport(
                    subject=subject,
                    field=field,
                    values=values,
                    evidence_ids=sorted(set(evidence_ids[(subject, field)])),
                    reason="conflicting_field_values",
                )
            )
        return reports


def _subject(evidence: CognitiveEvidence) -> str:
    return str(
        evidence.provenance.get("blueprint_node_id")
        or evidence.payload.get("subject")
        or evidence.payload.get("node_id")
        or evidence.evidence_type
    )


def _claims(evidence: CognitiveEvidence) -> dict[str, Any]:
    claims = evidence.payload.get("claims")
    if isinstance(claims, dict):
        return claims
    return {
        key: value
        for key, value in evidence.payload.items()
        if key not in {"metadata", "subject", "node_id", "blueprint_node_id", "expiration_seconds"}
    }
