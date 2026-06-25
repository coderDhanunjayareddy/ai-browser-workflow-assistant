"""
Unit tests for V5.0 Mission domain models.
Covers: MissionState, VALID_MISSION_TRANSITIONS, TERMINAL_MISSION_STATES,
        Mission dataclass, create_mission factory.
"""
import pytest
from datetime import datetime

from app.mission.models import (
    Mission, MissionState, TERMINAL_MISSION_STATES,
    VALID_MISSION_TRANSITIONS, create_mission, MissionEventType,
    MissionTimelineEvent,
)


# ── MissionState ──────────────────────────────────────────────────────────────

class TestMissionState:
    def test_values_are_uppercase_strings(self):
        assert MissionState.created.value == "CREATED"
        assert MissionState.active.value == "ACTIVE"
        assert MissionState.paused.value == "PAUSED"
        assert MissionState.completed.value == "COMPLETED"
        assert MissionState.failed.value == "FAILED"
        assert MissionState.abandoned.value == "ABANDONED"

    def test_six_states(self):
        assert len(list(MissionState)) == 6

    def test_is_str_subclass(self):
        assert isinstance(MissionState.created, str)


# ── Terminal states ───────────────────────────────────────────────────────────

class TestTerminalStates:
    def test_three_terminal_states(self):
        assert len(TERMINAL_MISSION_STATES) == 3

    def test_completed_is_terminal(self):
        assert MissionState.completed in TERMINAL_MISSION_STATES

    def test_failed_is_terminal(self):
        assert MissionState.failed in TERMINAL_MISSION_STATES

    def test_abandoned_is_terminal(self):
        assert MissionState.abandoned in TERMINAL_MISSION_STATES

    def test_created_not_terminal(self):
        assert MissionState.created not in TERMINAL_MISSION_STATES

    def test_active_not_terminal(self):
        assert MissionState.active not in TERMINAL_MISSION_STATES

    def test_paused_not_terminal(self):
        assert MissionState.paused not in TERMINAL_MISSION_STATES


# ── Transitions ───────────────────────────────────────────────────────────────

class TestTransitions:
    def test_created_can_become_active(self):
        assert MissionState.active in VALID_MISSION_TRANSITIONS[MissionState.created]

    def test_created_can_become_abandoned(self):
        assert MissionState.abandoned in VALID_MISSION_TRANSITIONS[MissionState.created]

    def test_active_can_pause(self):
        assert MissionState.paused in VALID_MISSION_TRANSITIONS[MissionState.active]

    def test_active_can_complete(self):
        assert MissionState.completed in VALID_MISSION_TRANSITIONS[MissionState.active]

    def test_active_can_fail(self):
        assert MissionState.failed in VALID_MISSION_TRANSITIONS[MissionState.active]

    def test_paused_can_resume(self):
        assert MissionState.active in VALID_MISSION_TRANSITIONS[MissionState.paused]

    def test_terminal_states_have_no_transitions(self):
        for state in TERMINAL_MISSION_STATES:
            assert VALID_MISSION_TRANSITIONS[state] == set()


# ── Mission dataclass ─────────────────────────────────────────────────────────

class TestMission:
    def test_is_terminal_false_for_active(self):
        m = create_mission("test")
        m.state = MissionState.active
        assert not m.is_terminal

    def test_is_terminal_true_for_completed(self):
        m = create_mission("test")
        m.state = MissionState.completed
        assert m.is_terminal

    def test_task_count_property(self):
        m = create_mission("test")
        m.task_ids = ["a", "b"]
        assert m.task_count == 2

    def test_touch_updates_updated_at(self):
        m = create_mission("test")
        before = m.updated_at
        import time; time.sleep(0.001)
        m.touch()
        assert m.updated_at >= before

    def test_default_state_is_created(self):
        m = create_mission("test")
        assert m.state == MissionState.created

    def test_default_priority_is_3(self):
        m = create_mission("test")
        assert m.priority == 3

    def test_priority_clamped_low(self):
        m = create_mission("test", priority=0)
        assert m.priority == 1

    def test_priority_clamped_high(self):
        m = create_mission("test", priority=99)
        assert m.priority == 5

    def test_mission_id_short_uuid(self):
        m = create_mission("title")
        assert len(m.mission_id) >= 12

    def test_empty_task_ids_by_default(self):
        m = create_mission("title")
        assert m.task_ids == []


# ── MissionTimelineEvent ──────────────────────────────────────────────────────

class TestMissionTimelineEvent:
    def test_create_basic_event(self):
        ev = MissionTimelineEvent(
            event_id="evt-001",
            event_type=MissionEventType.mission_created,
            mission_id="m1",
            task_id=None,
            data={"title": "test"},
        )
        assert ev.event_type == MissionEventType.mission_created
        assert ev.task_id is None

    def test_event_type_values(self):
        assert MissionEventType.task_attached.value == "task_attached"
        assert MissionEventType.mission_completed.value == "mission_completed"
