"""
V6.0 Unit Tests — TabSnapshotManager (16 tests).
"""
import pytest

from app.tabs.snapshot import TabSnapshotManager, SNAPSHOT_TRIGGERS
from app.tabs.models import create_tab, BrowserTabRole, BrowserTabState
from app.tabs import analytics as tab_analytics


@pytest.fixture(autouse=True)
def reset():
    tab_analytics._reset_for_testing()
    yield


def _tab(tab_id="t1", role=BrowserTabRole.research, mission_id=None):
    t = create_tab("https://example.com", "Example", role, tab_id=tab_id)
    t.mission_id = mission_id
    return t


class TestCreate:
    def test_create_returns_snapshot_id(self):
        mgr = TabSnapshotManager()
        tab = _tab()
        sid = mgr.create(tab, "tab_registered")
        assert sid is not None
        assert len(sid) > 10

    def test_create_unknown_trigger_returns_none(self):
        mgr = TabSnapshotManager()
        tab = _tab()
        assert mgr.create(tab, "unknown_trigger") is None

    def test_all_triggers_accepted(self):
        mgr = TabSnapshotManager()
        tab = _tab()
        for trigger in SNAPSHOT_TRIGGERS:
            assert mgr.create(tab, trigger) is not None

    def test_snapshot_count_increments(self):
        mgr = TabSnapshotManager()
        tab = _tab()
        mgr.create(tab, "tab_registered")
        mgr.create(tab, "mission_linked")
        assert mgr.count("t1") == 2

    def test_snapshot_context_has_expected_keys(self):
        mgr = TabSnapshotManager()
        tab = _tab(mission_id="m1")
        mgr.create(tab, "mission_linked")
        ctx = mgr.load_latest("t1")
        assert ctx["tab_id"]     == "t1"
        assert ctx["url"]        == "https://example.com"
        assert ctx["role"]       == "RESEARCH"
        assert ctx["mission_id"] == "m1"
        assert ctx["trigger"]    == "mission_linked"
        assert "snapshot_id" in ctx
        assert "created_at"  in ctx


class TestLoad:
    def test_load_latest_returns_most_recent(self):
        mgr = TabSnapshotManager()
        tab = _tab()
        mgr.create(tab, "tab_registered")
        tab.url = "https://updated.com"
        mgr.create(tab, "tab_role_changed")
        ctx = mgr.load_latest("t1")
        assert ctx["trigger"] == "tab_role_changed"

    def test_load_latest_returns_none_when_empty(self):
        mgr = TabSnapshotManager()
        assert mgr.load_latest("nonexistent") is None

    def test_load_all_newest_first(self):
        mgr = TabSnapshotManager()
        tab = _tab()
        mgr.create(tab, "tab_registered")
        mgr.create(tab, "mission_linked")
        mgr.create(tab, "tab_closed")
        all_snaps = mgr.load_all("t1")
        assert len(all_snaps) == 3
        assert all_snaps[0]["trigger"] == "tab_closed"
        assert all_snaps[-1]["trigger"] == "tab_registered"

    def test_load_all_empty_returns_list(self):
        mgr = TabSnapshotManager()
        assert mgr.load_all("nonexistent") == []

    def test_snapshots_are_independent_copies(self):
        mgr = TabSnapshotManager()
        tab = _tab()
        mgr.create(tab, "tab_registered")
        ctx = mgr.load_latest("t1")
        ctx["url"] = "mutated"
        ctx2 = mgr.load_latest("t1")
        assert ctx2["url"] == "https://example.com"   # original unchanged


class TestTabIds:
    def test_all_tab_ids_lists_registered(self):
        mgr = TabSnapshotManager()
        mgr.create(_tab("t1"), "tab_registered")
        mgr.create(_tab("t2"), "tab_registered")
        ids = mgr.all_tab_ids()
        assert "t1" in ids
        assert "t2" in ids

    def test_all_tab_ids_empty(self):
        mgr = TabSnapshotManager()
        assert mgr.all_tab_ids() == []


class TestReset:
    def test_reset_clears_all_snapshots(self):
        mgr = TabSnapshotManager()
        mgr.create(_tab("t1"), "tab_registered")
        mgr._reset_for_testing()
        assert mgr.all_tab_ids() == []
        assert mgr.load_latest("t1") is None

    def test_count_after_reset_is_zero(self):
        mgr = TabSnapshotManager()
        mgr.create(_tab("t1"), "tab_registered")
        mgr._reset_for_testing()
        assert mgr.count("t1") == 0

    def test_analytics_incremented_per_snapshot(self):
        from app.tabs.analytics import get_analytics
        mgr = TabSnapshotManager()
        tab_analytics._reset_for_testing()
        mgr.create(_tab(), "tab_registered")
        mgr.create(_tab(), "mission_linked")
        a = get_analytics()
        assert a["tab_snapshots"] == 2
