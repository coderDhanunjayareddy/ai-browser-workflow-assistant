"""
V7.0 Unit Tests — LiveSyncService (20 tests).
"""
import pytest

from app.browser.models import BrowserEventType, make_event
from app.browser.sync_service import LiveSyncService, SyncResult, process_event
from app.tabs import registry as tab_reg
from app.tabs.models import BrowserTabState, BrowserTabRole


@pytest.fixture(autouse=True)
def reset_tabs():
    tab_reg._reset_for_testing()
    yield
    tab_reg._reset_for_testing()


@pytest.fixture
def svc():
    return LiveSyncService()


def _ev(et, tab_id="t-sync", **kw):
    return make_event(et, tab_id, **kw)


class TestTabCreated:
    def test_creates_new_tab(self, svc):
        ev = _ev(BrowserEventType.tab_created, url="https://a.com", title="A")
        result = svc.process_event(ev)
        assert result.success is True
        assert result.tab_updated is True
        tab = tab_reg.get("t-sync")
        assert tab is not None
        assert tab.url == "https://a.com"

    def test_triggers_refresh(self, svc):
        ev = _ev(BrowserEventType.tab_created)
        result = svc.process_event(ev)
        assert result.triggers_refresh is True

    def test_mission_id_propagated(self, svc):
        ev = _ev(BrowserEventType.tab_created, mission_id="m1")
        result = svc.process_event(ev)
        assert result.mission_id == "m1"
        tab = tab_reg.get("t-sync")
        assert tab.mission_id == "m1"

    def test_duplicate_created_does_not_double_register(self, svc):
        ev = _ev(BrowserEventType.tab_created)
        svc.process_event(ev)
        svc.process_event(ev)
        # Should not raise; tab still exists
        assert tab_reg.get("t-sync") is not None


class TestTabActivated:
    def test_sets_active_state(self, svc):
        tab_reg.register(tab_id="t-sync", url="https://x.com", title="X",
                         role=BrowserTabRole.research)
        ev = _ev(BrowserEventType.tab_activated)
        result = svc.process_event(ev)
        assert result.success is True
        tab = tab_reg.get("t-sync")
        assert tab.state == BrowserTabState.active

    def test_does_not_trigger_refresh(self, svc):
        ev = _ev(BrowserEventType.tab_activated)
        result = svc.process_event(ev)
        assert result.triggers_refresh is False


class TestTabClosed:
    def test_closes_existing_tab(self, svc):
        tab_reg.register(tab_id="t-sync", url="u", title="T",
                         role=BrowserTabRole.research, mission_id="m2")
        ev = _ev(BrowserEventType.tab_closed, mission_id="m2")
        result = svc.process_event(ev)
        assert result.success is True
        assert result.triggers_refresh is True
        tab = tab_reg.get("t-sync")
        assert tab.state == BrowserTabState.closed

    def test_close_unknown_tab_succeeds(self, svc):
        ev = _ev(BrowserEventType.tab_closed, tab_id="unknown-tab")
        result = svc.process_event(ev)
        assert result.success is True


class TestUrlChanged:
    def test_updates_url(self, svc):
        tab_reg.register(tab_id="t-sync", url="https://old.com", title="Old",
                         role=BrowserTabRole.research)
        ev = _ev(BrowserEventType.url_changed, url="https://new.com")
        result = svc.process_event(ev)
        assert result.success is True
        assert result.triggers_refresh is True
        tab = tab_reg.get("t-sync")
        assert tab.url == "https://new.com"

    def test_url_changed_unknown_tab_succeeds(self, svc):
        ev = _ev(BrowserEventType.url_changed, tab_id="new-tab",
                 url="https://x.com")
        result = svc.process_event(ev)
        assert result.success is True


class TestPageLoaded:
    def test_updates_url_and_title(self, svc):
        tab_reg.register(tab_id="t-sync", url="about:blank", title="",
                         role=BrowserTabRole.research)
        ev = _ev(BrowserEventType.page_loaded,
                 url="https://final.com", title="Final Page")
        result = svc.process_event(ev)
        assert result.success is True
        assert result.triggers_refresh is True
        tab = tab_reg.get("t-sync")
        assert tab.url   == "https://final.com"
        assert tab.title == "Final Page"


class TestWindowEvents:
    def test_window_focused_no_tab_change(self, svc):
        ev = _ev(BrowserEventType.window_focused)
        result = svc.process_event(ev)
        assert result.success is True
        assert result.tab_updated is False
        assert result.triggers_refresh is False

    def test_window_blurred_no_tab_change(self, svc):
        ev = _ev(BrowserEventType.window_blurred)
        result = svc.process_event(ev)
        assert result.success is True
        assert result.triggers_refresh is False


class TestTabUpdated:
    def test_updates_existing_tab(self, svc):
        tab_reg.register(tab_id="t-sync", url="u", title="Old",
                         role=BrowserTabRole.research)
        ev = _ev(BrowserEventType.tab_updated, title="New Title")
        result = svc.process_event(ev)
        assert result.success is True
        tab = tab_reg.get("t-sync")
        assert tab.title == "New Title"

    def test_does_not_trigger_refresh(self, svc):
        ev = _ev(BrowserEventType.tab_updated)
        result = svc.process_event(ev)
        assert result.triggers_refresh is False


class TestSyncResult:
    def test_to_dict(self, svc):
        ev = _ev(BrowserEventType.tab_created)
        result = svc.process_event(ev)
        d = result.to_dict()
        for key in ("success", "event_id", "event_type", "tab_updated",
                    "triggers_refresh", "latency_ms"):
            assert key in d

    def test_module_level_process_event(self):
        ev = _ev(BrowserEventType.window_focused, tab_id="t-mod")
        result = process_event(ev)
        assert result.success is True

    def test_latency_ms_set(self, svc):
        ev = _ev(BrowserEventType.tab_created)
        result = svc.process_event(ev)
        assert result.latency_ms >= 0
