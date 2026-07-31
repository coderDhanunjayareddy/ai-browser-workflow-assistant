from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.cognitive_runtime.models import CognitiveMission
from app.cognitive_runtime.transitions import TransitionRecord


@dataclass(frozen=True)
class LifecycleSummary:
    mission_age_seconds: float
    transition_count: int
    active_duration_seconds: float
    wait_duration_seconds: float
    execution_duration_seconds: float
    recovery_duration_seconds: float
    replanning_count: int

    def to_dict(self) -> dict:
        return asdict(self)


class MissionLifecycleAnalyzer:
    """Computes passive lifecycle metrics from cognitive state history."""

    def analyze(
        self,
        *,
        mission: CognitiveMission,
        transitions: list[TransitionRecord] | None = None,
        now: datetime | None = None,
    ) -> LifecycleSummary:
        now = now or datetime.now(UTC)
        created = mission.created_at if mission.created_at.tzinfo else mission.created_at.replace(tzinfo=UTC)
        history = list(transitions or [])
        mission_age = max(0.0, (now - created).total_seconds())
        wait_count = sum(1 for item in history if item.to_state.value.startswith("waiting_"))
        execution_count = sum(1 for item in history if item.to_state.value == "executing")
        recovery_count = sum(1 for item in history if item.to_state.value == "recovering")
        replanning_count = sum(1 for item in history if item.to_state.value == "replanning")
        return LifecycleSummary(
            mission_age_seconds=round(mission_age, 4),
            transition_count=len(history),
            active_duration_seconds=round(mission_age, 4),
            wait_duration_seconds=float(wait_count),
            execution_duration_seconds=float(execution_count),
            recovery_duration_seconds=float(recovery_count),
            replanning_count=replanning_count,
        )
