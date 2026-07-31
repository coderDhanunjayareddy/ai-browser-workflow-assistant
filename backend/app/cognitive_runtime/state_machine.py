from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.models import CognitiveState
from app.cognitive_runtime.transitions import TransitionEngine


@dataclass(frozen=True)
class CognitiveStateSnapshot:
    state: CognitiveState
    reason: str
    expected_next: list[CognitiveState]
    blocked: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["expected_next"] = [state.value for state in self.expected_next]
        return data


class CognitiveStateMachine:
    """Determines passive cognitive mission state from diagnostics."""

    def __init__(self, transition_engine: TransitionEngine | None = None):
        self.transition_engine = transition_engine or TransitionEngine()

    def determine_state(
        self,
        *,
        evidence_count: int = 0,
        ready_nodes: list[str] | None = None,
        blocked_nodes: list[str] | None = None,
        waiting_nodes: list[str] | None = None,
        clarification_required: bool = False,
        wait_kind: str | None = None,
        recovery_status: str = "unknown",
        replanning_status: str = "unnecessary",
    ) -> CognitiveStateSnapshot:
        ready_nodes = list(ready_nodes or [])
        blocked_nodes = list(blocked_nodes or [])
        waiting_nodes = list(waiting_nodes or [])
        if replanning_status == "required":
            state, reason = CognitiveState.REPLANNING, "replanning_required"
        elif clarification_required:
            state, reason = CognitiveState.WAITING_USER, "clarification_required"
        elif wait_kind == "browser":
            state, reason = CognitiveState.WAITING_BROWSER, "browser_wait_detected"
        elif wait_kind in {"external", "authentication", "file", "network", "approval", "time"}:
            state, reason = CognitiveState.WAITING_EXTERNAL, f"{wait_kind}_wait_detected"
        elif recovery_status in {"recoverable", "partially_recoverable"}:
            state, reason = CognitiveState.RECOVERING, recovery_status
        elif ready_nodes:
            state, reason = CognitiveState.READY, "ready_nodes_available"
        elif blocked_nodes:
            state, reason = CognitiveState.BLOCKED, "blocked_nodes_present"
        elif waiting_nodes:
            state, reason = CognitiveState.WAITING_EXTERNAL, "waiting_nodes_present"
        elif evidence_count:
            state, reason = CognitiveState.EXECUTING, "evidence_available"
        else:
            state, reason = CognitiveState.INITIALIZED, "no_evidence"
        return CognitiveStateSnapshot(
            state=state,
            reason=reason,
            expected_next=sorted(self.transition_engine.diagnostics().allowed_next_states, key=lambda item: item.value),
            blocked=state == CognitiveState.BLOCKED,
            metadata={"execution_impact": "none"},
        )

    def validate_transition(self, from_state: CognitiveState, to_state: CognitiveState) -> bool:
        return self.transition_engine.can_transition(from_state, to_state)
