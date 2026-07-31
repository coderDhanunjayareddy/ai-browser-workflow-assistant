from __future__ import annotations

from app.cognitive_runtime.models import CognitiveEvidence, CognitiveMetrics


def compute_metrics(
    *,
    mission_id: str,
    evidence: list[CognitiveEvidence],
    previous: CognitiveMetrics | None = None,
) -> CognitiveMetrics:
    previous = previous or CognitiveMetrics(mission_id=mission_id)
    confidence_average = 0.0
    if evidence:
        confidence_average = sum(item.confidence for item in evidence) / len(evidence)
    clarification_count = sum(1 for item in evidence if item.evidence_type == "clarification_obtained")
    recovery_count = sum(1 for item in evidence if item.evidence_type in {"recovery_started", "recovery_completed"})
    replanning_count = sum(1 for item in evidence if item.evidence_type in {"replan_requested", "blueprint_revised"})
    return CognitiveMetrics(
        mission_id=mission_id,
        reasoning_iterations=previous.reasoning_iterations,
        clarification_count=clarification_count,
        evidence_count=len(evidence),
        confidence_average=round(confidence_average, 4),
        recovery_count=recovery_count,
        replanning_count=replanning_count,
        execution_duration_ms=previous.execution_duration_ms,
        metadata=dict(previous.metadata),
    )
