from __future__ import annotations

import time
from typing import Any

from app.mission.v3.fsm import MissionStateMachine
from app.mission.v3.models import MissionSnapshot
from app.mission.v3.telemetry import record_mission_metrics


class MissionIntelligenceEngine:
    """Shadow-capable deterministic mission state manager.

    This engine consumes existing workflow events and produces mission snapshots.
    It never creates planner actions, executes browser operations, or changes
    Planner Contract V2 outcomes.
    """

    def __init__(self):
        self._missions: dict[str, MissionStateMachine] = {}

    def ensure_mission(self, *, run_id: str, goal: str = "") -> MissionSnapshot:
        if run_id not in self._missions:
            self._missions[run_id] = MissionStateMachine.create(run_id=run_id, goal=goal)
        elif goal and not self._missions[run_id].snapshot.goal:
            self._missions[run_id].snapshot.goal = goal
            self._missions[run_id].snapshot.current_objective = goal
            self._missions[run_id].snapshot.remaining_objectives = [goal]
        return self._missions[run_id].clone_snapshot()

    def apply_workflow_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
        step_index: int = 0,
    ) -> tuple[MissionSnapshot, int]:
        started = time.perf_counter()
        goal = ""
        if payload:
            goal = str(payload.get("task") or payload.get("goal") or "")
        fsm = self._missions.setdefault(
            run_id,
            MissionStateMachine.create(run_id=run_id, goal=goal),
        )
        snapshot = fsm.apply_event(
            event_type=event_type,
            payload=payload or {},
            event_id=event_id,
            step_index=step_index,
        )
        transition_ms = int((time.perf_counter() - started) * 1000)
        record_mission_metrics(run_id, snapshot, transition_ms=transition_ms)
        return snapshot.model_copy(deep=True), transition_ms

    def pause(self, run_id: str) -> MissionSnapshot:
        fsm = self._missions.setdefault(run_id, MissionStateMachine.create(run_id=run_id))
        snapshot = fsm.pause()
        record_mission_metrics(run_id, snapshot, transition_ms=0)
        return snapshot.model_copy(deep=True)

    def resume(self, run_id: str) -> MissionSnapshot:
        fsm = self._missions.setdefault(run_id, MissionStateMachine.create(run_id=run_id))
        snapshot = fsm.resume()
        record_mission_metrics(run_id, snapshot, transition_ms=0)
        return snapshot.model_copy(deep=True)

    def get_snapshot(self, run_id: str) -> MissionSnapshot | None:
        fsm = self._missions.get(run_id)
        return fsm.clone_snapshot() if fsm else None

    def reset(self) -> None:
        self._missions.clear()
