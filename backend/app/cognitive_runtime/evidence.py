from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.cognitive_runtime.models import CognitiveEvidence, EvidenceCollection


def normalize_confidence(value: float | int | None) -> float:
    if value is None:
        return 1.0
    return max(0.0, min(1.0, float(value)))


def merge_evidence(*collections: EvidenceCollection) -> EvidenceCollection:
    if not collections:
        return EvidenceCollection(mission_id="")
    merged = collections[0]
    for collection in collections[1:]:
        merged = merged.merge(collection)
    return merged


def deduplicate_evidence(items: list[CognitiveEvidence]) -> list[CognitiveEvidence]:
    return list(EvidenceCollection(mission_id=items[0].mission_id if items else "", evidence=tuple(items)).deduplicate().evidence)


def evidence_freshness_seconds(evidence: CognitiveEvidence, *, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    timestamp = evidence.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return max(0.0, (now - timestamp).total_seconds())


def provenance_lookup(collection: EvidenceCollection, key: str, value: Any) -> list[CognitiveEvidence]:
    return collection.provenance_lookup(key, value)
