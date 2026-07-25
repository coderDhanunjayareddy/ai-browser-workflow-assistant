from __future__ import annotations

from app.runtime_state_manager.models import RuntimeArtifact


def artifact_completion_status(required_phase: str, artifacts: list[RuntimeArtifact], required_count: int = 1) -> dict[str, object]:
    phase = required_phase.upper()
    relevant = [
        artifact for artifact in artifacts
        if artifact.owner_phase == phase and artifact.completion_status == "complete" and artifact.validation_status in {"valid", "unknown"}
    ]
    return {
        "phase": phase,
        "required_count": required_count,
        "complete_count": len(relevant),
        "complete": len(relevant) >= required_count,
        "artifact_ids": [artifact.logical_id for artifact in relevant[:required_count]],
    }
