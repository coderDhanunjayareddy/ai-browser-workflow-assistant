"""
Unit tests for V5.0 MissionLifecycleManager.
Covers: create, attach_task, detach_task, pause/resume/complete/fail/abandon,
        auto-evaluation of mission state from task states.
"""
import pytest

from app.mission import lifecycle as mission_lifecycle, store as mission_store
from app.mission.models import MissionState, create_mission
from app.mission.lifecycle import MissionError
from app.mission import analytics as mission_analytics


@pytest.fixture(autouse=True)
def reset_store():
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()


class TestCreate:
    def test_creates_mission_in_store(self):
        m = mission_lifecycle.create_mission_obj("My Mission")
        assert mission_store.get(m.mission_id) is not None

    def test_default_state_created(self):
        m = mission_lifecycle.create_mission_obj("T")
        assert m.state == MissionState.created

    def test_analytics_incremented(self):
        mission_lifecycle.create_mission_obj("T")
        analytics = mission_analytics.get_analytics()
        assert analytics["total_missions"] == 1
        assert analytics["active_missions"] == 1

    def test_priority_clamped(self):
        m = mission_lifecycle.create_mission_obj("T", priority=10)
        assert m.priority == 5


class TestAttachTask:
    def test_attach_adds_task_id(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "task-1")
        updated = mission_store.get(m.mission_id)
        assert "task-1" in updated.task_ids

    def test_attach_promotes_to_active(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "task-1")
        updated = mission_store.get(m.mission_id)
        assert updated.state == MissionState.active

    def test_attach_is_idempotent(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "task-1")
        mission_lifecycle.attach_task(m.mission_id, "task-1")
        updated = mission_store.get(m.mission_id)
        assert updated.task_ids.count("task-1") == 1

    def test_attach_to_terminal_raises(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "task-1")
        mission_lifecycle.complete(m.mission_id)
        with pytest.raises(MissionError):
            mission_lifecycle.attach_task(m.mission_id, "task-2")

    def test_attach_analytics(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "task-x")
        assert mission_analytics.get_analytics()["total_tasks_attached"] == 1


class TestDetachTask:
    def test_detach_removes_task_id(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "task-1")
        mission_lifecycle.detach_task(m.mission_id, "task-1")
        updated = mission_store.get(m.mission_id)
        assert "task-1" not in updated.task_ids

    def test_detach_idempotent(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.detach_task(m.mission_id, "nonexistent")  # no raise

    def test_detach_unknown_mission_raises(self):
        with pytest.raises(MissionError):
            mission_lifecycle.detach_task("no-such-mission", "t1")


class TestPauseResume:
    def test_active_can_pause(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "t1")
        mission_lifecycle.pause(m.mission_id)
        assert mission_store.get(m.mission_id).state == MissionState.paused

    def test_paused_can_resume(self):
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "t1")
        mission_lifecycle.pause(m.mission_id)
        mission_lifecycle.resume(m.mission_id)
        assert mission_store.get(m.mission_id).state == MissionState.active

    def test_created_cannot_pause(self):
        m = mission_lifecycle.create_mission_obj("M")
        with pytest.raises(MissionError):
            mission_lifecycle.pause(m.mission_id)


class TestCompleteFailAbandon:
    def _active(self) -> str:
        m = mission_lifecycle.create_mission_obj("M")
        mission_lifecycle.attach_task(m.mission_id, "t1")
        return m.mission_id

    def test_complete_sets_state(self):
        mid = self._active()
        mission_lifecycle.complete(mid)
        assert mission_store.get(mid).state == MissionState.completed

    def test_fail_sets_state(self):
        mid = self._active()
        mission_lifecycle.fail(mid, "DB error")
        m = mission_store.get(mid)
        assert m.state == MissionState.failed
        assert m.metadata.get("failure_reason") == "DB error"

    def test_abandon_sets_state(self):
        mid = self._active()
        mission_lifecycle.abandon(mid)
        assert mission_store.get(mid).state == MissionState.abandoned

    def test_complete_analytics(self):
        mid = self._active()
        mission_lifecycle.complete(mid)
        assert mission_analytics.get_analytics()["completed_missions"] == 1

    def test_cannot_transition_from_terminal(self):
        mid = self._active()
        mission_lifecycle.complete(mid)
        with pytest.raises(MissionError):
            mission_lifecycle.fail(mid)


class TestNotFoundError:
    def test_unknown_mission_raises(self):
        with pytest.raises(MissionError):
            mission_lifecycle.complete("ghost-id")
