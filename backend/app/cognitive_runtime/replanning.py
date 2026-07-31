from __future__ import annotations

from dataclasses import asdict, dataclass

from app.cognitive_runtime.models import EvidenceCollection


@dataclass(frozen=True)
class ReplanningDiagnostics:
    recommendation: str
    reasons: list[str]
    contradiction_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class ReplanningEvaluator:
    """Determines passive replanning recommendation without invoking a planner."""

    def evaluate(self, evidence: EvidenceCollection, *, contradiction_count: int = 0) -> ReplanningDiagnostics:
        reasons: list[str] = []
        if contradiction_count:
            reasons.append("contradictory_evidence")
        for item in evidence.evidence:
            if item.evidence_type in {"blueprint_invalidated", "critical_path_unreachable", "objective_changed"}:
                reasons.append(item.evidence_type)
            elif item.evidence_type in {"validation_failed", "missing_required_evidence"}:
                reasons.append(item.evidence_type)
        if any(reason in {"blueprint_invalidated", "critical_path_unreachable", "objective_changed"} for reason in reasons):
            recommendation = "required"
        elif reasons:
            recommendation = "recommended"
        else:
            recommendation = "unnecessary"
        return ReplanningDiagnostics(
            recommendation=recommendation,
            reasons=sorted(set(reasons)),
            contradiction_count=contradiction_count,
        )
