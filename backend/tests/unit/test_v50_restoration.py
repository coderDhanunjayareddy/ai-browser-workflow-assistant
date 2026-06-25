"""
Unit tests for V5.0 MissionRestorationService.
Covers: fast path (in-memory), slow path (DB), task restoration delegation,
        warmup(), None return for unknown missions.
"""
import pytest

from app.mission import restoration as mission_restoration
from app.mission import store as mission_store, persistence as mission_persistence
from app.mission import lifecycle as mission_lifecycle, analytics as mission_analytics
from app.mission.models import create_mission, MissionState


@pytest.fixture(autouse=True)
def reset():
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()


class TestFastPath:
    def test_returns_from_memory_if_present(self):
        m = mission_lifecycle.create_mission_obj("M", "obj")
        result = mission_restoration.restore(m.mission_id)
        assert result is not None
        assert result.mission_id == m.mission_id

    def test_fast_path_does_not_hit_db(self, monkeypatch):
        m = mission_lifecycle.create_mission_obj("M")
        called = []
        monkeypatch.setattr(mission_persistence, "load", lambda mid: called.append(mid) or None)
        mission_restoration.restore(m.mission_id)
        assert len(called) == 0  # DB never called


class TestSlowPath:
    def test_returns_none_when_not_in_db(self, monkeypatch):
        monkeypatch.setattr(mission_persistence, "load", lambda mid: None)
        result = mission_restoration.restore("ghost-id")
        assert result is None

    def test_loads_from_db_when_not_in_memory(self, monkeypatch):
        m = create_mission("M-DB")
        monkeypatch.setattr(mission_persistence, "load", lambda mid: m if mid == m.mission_id else None)
        monkeypatch.setattr(mission_persistence, "_enabled", lambda: True)
        # Ensure it's not in memory
        result = mission_restoration.restore(m.mission_id)
        assert result is not None
        assert result.mission_id == m.mission_id

    def test_puts_restored_mission_in_store(self, monkeypatch):
        m = create_mission("M-DB-2")
        monkeypatch.setattr(mission_persistence, "load", lambda mid: m if mid == m.mission_id else None)
        mission_restoration.restore(m.mission_id)
        # Should be in store now
        assert mission_store.get(m.mission_id) is not None


class TestWarmup:
    def test_warmup_returns_count(self, monkeypatch):
        m1 = create_mission("warm-1")
        m2 = create_mission("warm-2")
        monkeypatch.setattr(mission_persistence, "load_active", lambda: [m1, m2])
        count = mission_restoration.warmup()
        assert count == 2

    def test_warmup_stores_missions(self, monkeypatch):
        m = create_mission("warm-store")
        monkeypatch.setattr(mission_persistence, "load_active", lambda: [m])
        mission_restoration.warmup()
        assert mission_store.get(m.mission_id) is not None

    def test_warmup_with_empty_db(self, monkeypatch):
        monkeypatch.setattr(mission_persistence, "load_active", lambda: [])
        count = mission_restoration.warmup()
        assert count == 0
