from __future__ import annotations

from app.execution_orchestrator.models import PhaseState, TransitionRecord


def build_transitions(phases: list[PhaseState]) -> list[TransitionRecord]:
    transitions: list[TransitionRecord] = []
    completed = [phase for phase in phases if phase.status == "complete"]
    active = next((phase for phase in phases if phase.status == "active"), None)
    ordered = completed + ([active] if active else [])
    for prev, curr in zip(ordered, ordered[1:]):
        transitions.append(
            TransitionRecord(
                from_phase=prev.name,
                to_phase=curr.name,
                reason=prev.completion_reason or "previous phase complete",
            )
        )
    return transitions
