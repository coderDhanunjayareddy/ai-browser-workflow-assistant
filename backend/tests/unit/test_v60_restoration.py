"""
V6.0 Unit Tests — TabRestorationService (14 tests).
"""
import pytest

from app.tabs.restoration import TabRestorationService
from app.tabs.snapshot import TabSnapshotManager
from app.tabs.registry import TabRegistry
from app.tabs.models import BrowserTabRole, BrowserTabState, create_tab
from app.tabs import analytics as tab_analytics
import app.tabs.registry as global_reg
import app.tabs.snapshot as global_snap


@pytest.fixture(autouse=True)
def reset():
    global_reg._reset_for_testing()
    global_snap._reset_for_testing()
    tab_analytics._reset_for_testing()
    yield
    global_reg._reset_for_testing()
    global_snap._reset_for_testing()
    tab_analytics._reset_for_testing()


def _snap_tab(tab_id, role=BrowserTabRole.research, mission_id=None,
              state=BrowserTabState.open, trigger="tab_registered"):
    tab = create_tab("https://example.com/" + tab_id, tab_id, role,
                     state=state, tab_id=tab_id)
    tab.mission_id = mission_id
    global_snap.create(tab, trigger)
    return tab


class TestRestoreAll:
    def test_restore_all_empty_snapshots(self):
        svc = TabRestorationService()
        result = svc.restore_all()
        assert result.tabs_restored == 0
        assert result.tabs_skipped  == 0
        assert result.success is True

    def test_restores_single_tab(self):
        _snap_tab("t1")
        svc = TabRestorationService()
        result = svc.restore_all()
        assert result.tabs_restored == 1
        # Tab should now be in registry as BACKGROUND
        tab = global_reg.get("t1")
        assert tab is not None
        assert tab.state == BrowserTabState.background

    def test_restores_multiple_tabs(self):
        _snap_tab("t1")
        _snap_tab("t2")
        _snap_tab("t3")
        svc = TabRestorationService()
        result = svc.restore_all()
        assert result.tabs_restored == 3

    def test_skips_closed_tabs(self):
        _snap_tab("t1", state=BrowserTabState.closed, trigger="tab_closed")
        svc = TabRestorationService()
        result = svc.restore_all()
        assert result.tabs_restored == 0
        assert result.tabs_skipped  == 1

    def test_restored_tabs_are_background_not_active(self):
        _snap_tab("t1", state=BrowserTabState.active)
        svc = TabRestorationService()
        svc.restore_all()
        tab = global_reg.get("t1")
        assert tab.state == BrowserTabState.background

    def test_mission_link_restored(self):
        _snap_tab("t1", mission_id="m1")
        svc = TabRestorationService()
        result = svc.restore_all()
        assert result.mission_links == 1
        tab = global_reg.get("t1")
        assert tab.mission_id == "m1"

    def test_result_is_successful(self):
        _snap_tab("t1")
        svc = TabRestorationService()
        result = svc.restore_all()
        assert result.success is True
        assert result.errors == []


class TestRestoreForMission:
    def test_restores_only_mission_tabs(self):
        _snap_tab("t1", mission_id="m1")
        _snap_tab("t2", mission_id="m2")
        _snap_tab("t3", mission_id="m1")
        svc = TabRestorationService()
        result = svc.restore_for_mission("m1")
        assert result.tabs_restored == 2
        # t2 should NOT be in registry yet
        assert global_reg.get("t2") is None

    def test_empty_when_no_mission_match(self):
        _snap_tab("t1", mission_id="m1")
        svc = TabRestorationService()
        result = svc.restore_for_mission("m99")
        assert result.tabs_restored == 0

    def test_analytics_record_restored(self):
        tab_analytics._reset_for_testing()
        _snap_tab("t1", mission_id="m1")
        svc = TabRestorationService()
        svc.restore_for_mission("m1")
        a = tab_analytics.get_analytics()
        assert a["tabs_restored"] == 1


class TestRestorationIdempotency:
    def test_second_restore_updates_not_duplicates(self):
        _snap_tab("t1")
        svc = TabRestorationService()
        svc.restore_all()
        result2 = svc.restore_all()
        # Should update, not add a second entry
        assert global_reg.count() == 1
        assert result2.tabs_restored == 1

    def test_role_preserved_from_snapshot(self):
        _snap_tab("t1", role=BrowserTabRole.comparison)
        svc = TabRestorationService()
        svc.restore_all()
        tab = global_reg.get("t1")
        assert tab.role == BrowserTabRole.comparison
