"""
V5.0 Mission Layer — MissionLifecycleManager.

Manages state transitions, task attachment/detachment, and auto-completion
logic for missions.

Auto-promotion rules (evaluated after every task state change):
  All tasks completed  → mission completed
  All tasks abandoned  → mission abandoned
  Any task active      → mission active (if currently created/paused)
  Any task failed, others not active → mission failed
"""
from __future__ import annotations

import logging
from typing import Optional

from app.mission.models import (
    Mission, MissionState, VALID_MISSION_TRANSITIONS,
    TERMINAL_MISSION_STATES, create_mission, MissionEventType,
)
from app.mission import store as mission_store, analytics as mission_analytics

logger = logging.getLogger(__name__)

TASK_STATE_TERMINAL  = {"COMPLETED", "ABANDONED", "FAILED"}
TASK_STATE_COMPLETED = {"COMPLETED"}
TASK_STATE_ABANDONED = {"ABANDONED"}
TASK_STATE_FAILED    = {"FAILED"}


class MissionError(Exception):
    pass


class MissionLifecycleManager:

    # ── Creation ──────────────────────────────────────────────────────────────

    def create(
        self,
        title: str,
        objective: str = "",
        priority: int = 3,
        mission_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Mission:
        mission = create_mission(
            title=title,
            objective=objective or title,
            priority=priority,
            mission_id=mission_id,
            metadata=metadata,
        )
        mission_store.put(mission)
        self._persist(mission)
        mission_analytics.record_mission_created()
        logger.info("Mission %s created: %r", mission.mission_id, title)
        return mission

    # ── Task attachment ───────────────────────────────────────────────────────

    def attach_task(self, mission_id: str, task_id: str) -> Mission:
        mission = self._require(mission_id)
        if mission.is_terminal:
            raise MissionError(
                f"Cannot attach task to terminal mission {mission_id} (state={mission.state.value})"
            )
        if task_id in mission.task_ids:
            return mission  # idempotent
        mission.task_ids.append(task_id)
        mission.touch()
        # Auto-promote to ACTIVE if still CREATED/PAUSED
        if mission.state in (MissionState.created, MissionState.paused):
            self._transition(mission, MissionState.active)
        mission_store.put(mission)
        self._persist(mission)
        mission_analytics.record_task_attached()
        return mission

    def detach_task(self, mission_id: str, task_id: str) -> Mission:
        mission = self._require(mission_id)
        if task_id not in mission.task_ids:
            return mission  # idempotent
        mission.task_ids.remove(task_id)
        mission.touch()
        mission_store.put(mission)
        self._persist(mission)
        self._auto_evaluate(mission)
        return mission

    # ── State transitions ─────────────────────────────────────────────────────

    def pause(self, mission_id: str) -> Mission:
        mission = self._require(mission_id)
        self._transition(mission, MissionState.paused)
        mission.touch()
        mission_store.put(mission)
        self._persist(mission)
        return mission

    def resume(self, mission_id: str) -> Mission:
        mission = self._require(mission_id)
        self._transition(mission, MissionState.active)
        mission.touch()
        mission_store.put(mission)
        self._persist(mission)
        return mission

    def complete(self, mission_id: str) -> Mission:
        mission = self._require(mission_id)
        self._transition(mission, MissionState.completed)
        mission.touch()
        mission_store.put(mission)
        self._persist(mission)
        mission_analytics.record_mission_completed()
        return mission

    def fail(self, mission_id: str, reason: str = "") -> Mission:
        mission = self._require(mission_id)
        self._transition(mission, MissionState.failed)
        mission.metadata["failure_reason"] = reason
        mission.touch()
        mission_store.put(mission)
        self._persist(mission)
        mission_analytics.record_mission_failed()
        return mission

    def abandon(self, mission_id: str) -> Mission:
        mission = self._require(mission_id)
        self._transition(mission, MissionState.abandoned)
        mission.touch()
        mission_store.put(mission)
        self._persist(mission)
        mission_analytics.record_mission_abandoned()
        return mission

    # ── Auto-evaluation ───────────────────────────────────────────────────────

    def on_task_state_changed(self, mission_id: str, task_id: str, new_task_state: str) -> None:
        """
        Called whenever a task's state changes.
        Evaluates whether the mission state should auto-transition.
        """
        mission = mission_store.get(mission_id)
        if mission is None or mission.is_terminal:
            return
        self._auto_evaluate(mission)

    def _auto_evaluate(self, mission: Mission) -> None:
        """Re-evaluate mission state from task states. No-op for terminal missions."""
        if mission.is_terminal or not mission.task_ids:
            return
        from app.unified import store as task_store
        task_states = set()
        for tid in mission.task_ids:
            t = task_store.get(tid)
            if t is not None:
                task_states.add(t.state.value)

        if not task_states:
            return  # tasks not loaded; can't evaluate

        if task_states <= TASK_STATE_COMPLETED:
            # All tasks are completed
            if not mission.is_terminal:
                self._transition(mission, MissionState.completed)
                mission.touch()
                mission_store.put(mission)
                self._persist(mission)
                mission_analytics.record_mission_completed()
        elif task_states <= TASK_STATE_ABANDONED:
            # All tasks are abandoned
            if not mission.is_terminal:
                self._transition(mission, MissionState.abandoned)
                mission.touch()
                mission_store.put(mission)
                self._persist(mission)
                mission_analytics.record_mission_abandoned()
        elif task_states <= TASK_STATE_TERMINAL and TASK_STATE_FAILED & task_states:
            # All terminal with at least one failure and no active tasks
            active_count = sum(1 for s in task_states if s not in TASK_STATE_TERMINAL)
            if active_count == 0 and not mission.is_terminal:
                self._transition(mission, MissionState.failed)
                mission.touch()
                mission_store.put(mission)
                self._persist(mission)
                mission_analytics.record_mission_failed()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _require(self, mission_id: str) -> Mission:
        mission = mission_store.get(mission_id)
        if mission is None:
            raise MissionError(f"Mission {mission_id!r} not found")
        return mission

    def _transition(self, mission: Mission, to_state: MissionState) -> None:
        allowed = VALID_MISSION_TRANSITIONS.get(mission.state, set())
        if to_state not in allowed:
            raise MissionError(
                f"Invalid mission transition {mission.state.value} → {to_state.value}"
            )
        logger.debug(
            "Mission %s: %s → %s", mission.mission_id,
            mission.state.value, to_state.value,
        )
        mission.state = to_state

    def _persist(self, mission: Mission) -> None:
        try:
            from app.mission import persistence as mission_persistence
            mission_persistence.save(mission)
        except Exception:
            logger.exception("mission lifecycle: persist failed for %s", mission.mission_id)


# Module-level singleton
_manager = MissionLifecycleManager()


def create_mission_obj(
    title: str,
    objective: str = "",
    priority: int = 3,
    mission_id: Optional[str] = None,
) -> Mission:
    return _manager.create(title, objective, priority, mission_id)


def attach_task(mission_id: str, task_id: str) -> Mission:
    return _manager.attach_task(mission_id, task_id)


def detach_task(mission_id: str, task_id: str) -> Mission:
    return _manager.detach_task(mission_id, task_id)


def pause(mission_id: str) -> Mission:
    return _manager.pause(mission_id)


def resume(mission_id: str) -> Mission:
    return _manager.resume(mission_id)


def complete(mission_id: str) -> Mission:
    return _manager.complete(mission_id)


def fail(mission_id: str, reason: str = "") -> Mission:
    return _manager.fail(mission_id, reason)


def abandon(mission_id: str) -> Mission:
    return _manager.abandon(mission_id)


def on_task_state_changed(mission_id: str, task_id: str, new_task_state: str) -> None:
    _manager.on_task_state_changed(mission_id, task_id, new_task_state)
