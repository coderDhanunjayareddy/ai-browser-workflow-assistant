from __future__ import annotations

from dataclasses import asdict, dataclass

from app.cognitive_runtime.models import EvidenceCollection


@dataclass(frozen=True)
class RecoveryDiagnostics:
    classification: str
    reasons: list[str]
    failure_count: int
    recovery_evidence_count: int

    def to_dict(self) -> dict:
        return asdict(self)


class RecoveryStateEvaluator:
    """Classifies passive recovery likelihood without triggering recovery."""

    def evaluate(self, evidence: EvidenceCollection) -> RecoveryDiagnostics:
        failures = [item for item in evidence.evidence if item.evidence_type in {"failure", "node_failed", "provider_failed"}]
        recoveries = [item for item in evidence.evidence if item.evidence_type in {"recovery_available", "recovery_started", "recovery_completed"}]
        blocked = [item for item in evidence.evidence if item.evidence_type in {"blocked", "node_blocked", "blueprint_node_blocked"}]
        if blocked and not recoveries:
            classification = "blocked"
        elif recoveries and failures:
            classification = "recoverable"
        elif failures and any(item.payload.get("partial") for item in failures):
            classification = "partially_recoverable"
        elif failures:
            classification = "unknown"
        else:
            classification = "unknown"
        return RecoveryDiagnostics(
            classification=classification,
            reasons=[item.evidence_type for item in [*failures, *recoveries, *blocked]],
            failure_count=len(failures),
            recovery_evidence_count=len(recoveries),
        )
