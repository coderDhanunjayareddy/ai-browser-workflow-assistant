from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from app.cognitive_runtime.models import CognitiveState


LEGAL_TRANSITIONS: dict[CognitiveState, set[CognitiveState]] = {
    CognitiveState.INITIALIZED: {CognitiveState.UNDERSTANDING, CognitiveState.READY, CognitiveState.CANCELLED},
    CognitiveState.UNDERSTANDING: {CognitiveState.READY, CognitiveState.WAITING_USER, CognitiveState.BLOCKED, CognitiveState.CANCELLED},
    CognitiveState.READY: {CognitiveState.EXECUTING, CognitiveState.WAITING_USER, CognitiveState.WAITING_EXTERNAL, CognitiveState.CANCELLED},
    CognitiveState.EXECUTING: {
        CognitiveState.WAITING_BROWSER,
        CognitiveState.WAITING_USER,
        CognitiveState.WAITING_EXTERNAL,
        CognitiveState.RECOVERING,
        CognitiveState.REPLANNING,
        CognitiveState.PARTIAL_SUCCESS,
        CognitiveState.COMPLETED,
        CognitiveState.FAILED,
        CognitiveState.BLOCKED,
    },
    CognitiveState.WAITING_BROWSER: {CognitiveState.EXECUTING, CognitiveState.RECOVERING, CognitiveState.BLOCKED, CognitiveState.CANCELLED},
    CognitiveState.WAITING_USER: {CognitiveState.READY, CognitiveState.EXECUTING, CognitiveState.REPLANNING, CognitiveState.BLOCKED, CognitiveState.CANCELLED},
    CognitiveState.WAITING_EXTERNAL: {CognitiveState.READY, CognitiveState.EXECUTING, CognitiveState.RECOVERING, CognitiveState.BLOCKED, CognitiveState.CANCELLED},
    CognitiveState.BLOCKED: {CognitiveState.RECOVERING, CognitiveState.REPLANNING, CognitiveState.FAILED, CognitiveState.CANCELLED},
    CognitiveState.RECOVERING: {CognitiveState.READY, CognitiveState.EXECUTING, CognitiveState.REPLANNING, CognitiveState.BLOCKED, CognitiveState.FAILED},
    CognitiveState.REPLANNING: {CognitiveState.UNDERSTANDING, CognitiveState.READY, CognitiveState.BLOCKED, CognitiveState.FAILED},
    CognitiveState.PARTIAL_SUCCESS: {CognitiveState.EXECUTING, CognitiveState.REPLANNING, CognitiveState.COMPLETED, CognitiveState.FAILED},
    CognitiveState.COMPLETED: set(),
    CognitiveState.FAILED: set(),
    CognitiveState.CANCELLED: set(),
}


@dataclass(frozen=True)
class TransitionRecord:
    from_state: CognitiveState
    to_state: CognitiveState
    legal: bool
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["from_state"] = self.from_state.value
        data["to_state"] = self.to_state.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class TransitionDiagnostics:
    current_state: CognitiveState
    allowed_next_states: list[CognitiveState]
    history: list[TransitionRecord]
    illegal_transition_count: int = 0

    def to_dict(self) -> dict:
        return {
            "current_state": self.current_state.value,
            "allowed_next_states": [state.value for state in self.allowed_next_states],
            "history": [item.to_dict() for item in self.history],
            "illegal_transition_count": self.illegal_transition_count,
        }


class TransitionEngine:
    """Validates cognitive state transitions without executing recovery or replanning."""

    def __init__(self, initial_state: CognitiveState = CognitiveState.INITIALIZED):
        self.current_state = initial_state
        self.history: list[TransitionRecord] = []

    def can_transition(self, from_state: CognitiveState, to_state: CognitiveState) -> bool:
        return to_state in LEGAL_TRANSITIONS.get(from_state, set())

    def transition(self, to_state: CognitiveState, *, reason: str) -> TransitionRecord:
        legal = self.can_transition(self.current_state, to_state)
        record = TransitionRecord(self.current_state, to_state, legal, reason if reason else "unspecified")
        self.history.append(record)
        if legal:
            self.current_state = to_state
        return record

    def diagnostics(self) -> TransitionDiagnostics:
        return TransitionDiagnostics(
            current_state=self.current_state,
            allowed_next_states=sorted(LEGAL_TRANSITIONS.get(self.current_state, set()), key=lambda state: state.value),
            history=list(self.history),
            illegal_transition_count=sum(1 for item in self.history if not item.legal),
        )
