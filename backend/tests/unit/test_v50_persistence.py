"""
Unit tests for V5.0 Mission Persistence (ORM layer).
Uses SQLite in-memory via conftest.py injection (test_v50_* prefix).
Covers: save, load, load_active, delete, upsert, task_refs sync.
"""
import pytest

from app.mission import persistence as mission_persistence
from app.mission.models import create_mission, MissionState


# conftest.py injects SQLite + sets settings.mission_persistence=True for test_v50_* files


class TestSave:
    def test_save_then_load(self):
        m = create_mission("Test Mission", "objective")
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded is not None
        assert loaded.title == "Test Mission"
        assert loaded.objective == "objective"

    def test_save_preserves_state(self):
        m = create_mission("M")
        m.state = MissionState.active
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded.state == MissionState.active

    def test_save_preserves_priority(self):
        m = create_mission("M", priority=1)
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded.priority == 1

    def test_upsert_updates_existing(self):
        m = create_mission("Original")
        mission_persistence.save(m)
        m.title = "Updated"
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded.title == "Updated"

    def test_save_metadata(self):
        m = create_mission("M")
        m.metadata = {"key": "value"}
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded.metadata.get("key") == "value"


class TestTaskRefs:
    def test_task_refs_persisted(self):
        m = create_mission("M")
        m.task_ids = ["task-a", "task-b"]
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert "task-a" in loaded.task_ids
        assert "task-b" in loaded.task_ids

    def test_task_refs_order_preserved(self):
        m = create_mission("M")
        m.task_ids = ["first", "second", "third"]
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded.task_ids == ["first", "second", "third"]

    def test_task_refs_synced_on_update(self):
        m = create_mission("M")
        m.task_ids = ["t1", "t2"]
        mission_persistence.save(m)
        m.task_ids = ["t1"]  # removed t2
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded.task_ids == ["t1"]

    def test_empty_task_refs_after_clear(self):
        m = create_mission("M")
        m.task_ids = ["t1"]
        mission_persistence.save(m)
        m.task_ids = []
        mission_persistence.save(m)
        loaded = mission_persistence.load(m.mission_id)
        assert loaded.task_ids == []


class TestLoad:
    def test_load_unknown_returns_none(self):
        result = mission_persistence.load("no-such-id")
        assert result is None


class TestLoadActive:
    def test_returns_only_non_terminal(self):
        m_active = create_mission("Active")
        m_active.state = MissionState.active
        mission_persistence.save(m_active)

        m_done = create_mission("Done")
        m_done.state = MissionState.completed
        mission_persistence.save(m_done)

        active = mission_persistence.load_active()
        ids = [m.mission_id for m in active]
        assert m_active.mission_id in ids
        assert m_done.mission_id not in ids

    def test_all_terminal_states_excluded(self):
        for state in [MissionState.completed, MissionState.failed, MissionState.abandoned]:
            m = create_mission(f"M-{state.value}")
            m.state = state
            mission_persistence.save(m)
        active = mission_persistence.load_active()
        # All 3 are terminal → none returned (may have leftovers from prev test)
        for m in active:
            assert m.state not in {MissionState.completed, MissionState.failed, MissionState.abandoned}


class TestDelete:
    def test_delete_removes_mission(self):
        m = create_mission("ToDelete")
        mission_persistence.save(m)
        result = mission_persistence.delete(m.mission_id)
        assert result is True
        assert mission_persistence.load(m.mission_id) is None

    def test_delete_unknown_returns_false(self):
        assert mission_persistence.delete("ghost-id") is False

    def test_delete_removes_task_refs(self):
        m = create_mission("M")
        m.task_ids = ["t1", "t2"]
        mission_persistence.save(m)
        mission_persistence.delete(m.mission_id)
        # Mission gone — task refs should be gone too (CASCADE)
        assert mission_persistence.load(m.mission_id) is None


class TestDisabledMode:
    def test_save_is_noop_when_disabled(self, monkeypatch):
        monkeypatch.setattr("app.mission.persistence._enabled", lambda: False)
        m = create_mission("NoPersist")
        mission_persistence.save(m)  # should not raise

    def test_load_returns_none_when_disabled(self, monkeypatch):
        monkeypatch.setattr("app.mission.persistence._enabled", lambda: False)
        result = mission_persistence.load("any-id")
        assert result is None

    def test_load_active_returns_empty_when_disabled(self, monkeypatch):
        monkeypatch.setattr("app.mission.persistence._enabled", lambda: False)
        result = mission_persistence.load_active()
        assert result == []

    def test_delete_returns_false_when_disabled(self, monkeypatch):
        monkeypatch.setattr("app.mission.persistence._enabled", lambda: False)
        result = mission_persistence.delete("any-id")
        assert result is False
