from __future__ import annotations

from app.execution_orchestrator.models import ArtifactRegistry, PhaseState, TransitionRecord


def phase_replay(phases: list[PhaseState], artifacts: ArtifactRegistry, transitions: list[TransitionRecord]) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for phase in phases:
        if phase.status in {"complete", "active", "failed", "blocked"}:
            frames.append({
                "event": "phase.started" if phase.status == "active" else "phase.completed",
                "phase": phase.name,
                "status": phase.status,
                "completion_reason": phase.completion_reason,
                "artifact_counts": artifacts.counts(),
            })
    for transition in transitions:
        frames.append({"event": "phase.transition", **transition.to_dict()})
    return frames[-20:]
