"""
V6.0 Unit Tests — TabRegistry (24 tests).
"""
import pytest

from app.tabs.registry import TabRegistry
from app.tabs.models import BrowserTabRole, BrowserTabState
from app.tabs import analytics as tab_analytics


@pytest.fixture(autouse=True)
def reset():
    tab_analytics._reset_for_testing()
    yield


def _reg() -> TabRegistry:
    return TabRegistry()


class TestRegister:
    def test_register_new_tab(self):
        reg = _reg()
        tab = reg.register("t1", "https://a.com", "A", BrowserTabRole.research)
        assert tab.tab_id == "t1"
        assert tab.url    == "https://a.com"
        assert tab.role   == BrowserTabRole.research

    def test_register_updates_existing(self):
        reg = _reg()
        reg.register("t1", "https://a.com", "A", BrowserTabRole.research)
        tab = reg.register("t1", "https://b.com", "B", BrowserTabRole.comparison)
        assert tab.url   == "https://b.com"
        assert tab.title == "B"
        assert tab.role  == BrowserTabRole.comparison

    def test_register_with_mission_and_task(self):
        reg = _reg()
        tab = reg.register("t1", "u", "t", BrowserTabRole.workflow,
                           mission_id="m1", task_id="task1")
        assert tab.mission_id == "m1"
        assert tab.task_id    == "task1"

    def test_register_returns_existing_on_id_collision(self):
        reg = _reg()
        t1 = reg.register("t1", "https://a.com", "A", BrowserTabRole.research)
        t2 = reg.register("t1", "https://b.com", "B", BrowserTabRole.comparison)
        # Same object
        assert t1 is t2

    def test_count_increments(self):
        reg = _reg()
        reg.register("t1", "u1", "T1", BrowserTabRole.research)
        reg.register("t2", "u2", "T2", BrowserTabRole.comparison)
        assert reg.count() == 2


class TestUpdate:
    def test_update_url(self):
        reg = _reg()
        reg.register("t1", "https://old.com", "Old", BrowserTabRole.research)
        tab = reg.update("t1", url="https://new.com")
        assert tab.url == "https://new.com"

    def test_update_state(self):
        reg = _reg()
        reg.register("t1", "u", "t", BrowserTabRole.research)
        tab = reg.update("t1", state=BrowserTabState.active)
        assert tab.state == BrowserTabState.active

    def test_update_returns_none_for_missing(self):
        reg = _reg()
        assert reg.update("missing", url="x") is None

    def test_set_active_sets_background_on_siblings(self):
        reg = _reg()
        reg.register("t1", "u1", "T1", BrowserTabRole.research,
                     state=BrowserTabState.active, mission_id="m1")
        reg.register("t2", "u2", "T2", BrowserTabRole.comparison,
                     state=BrowserTabState.open, mission_id="m1")
        reg.set_active("t2")
        assert reg.get("t1").state == BrowserTabState.background
        assert reg.get("t2").state == BrowserTabState.active

    def test_set_active_unknown_tab_returns_none(self):
        reg = _reg()
        assert reg.set_active("nope") is None


class TestClose:
    def test_close_sets_state(self):
        reg = _reg()
        reg.register("t1", "u", "t", BrowserTabRole.research)
        result = reg.close("t1")
        assert result is True
        assert reg.get("t1").state == BrowserTabState.closed

    def test_close_missing_returns_false(self):
        reg = _reg()
        assert reg.close("missing") is False

    def test_count_open_excludes_closed(self):
        reg = _reg()
        reg.register("t1", "u1", "T1", BrowserTabRole.research)
        reg.register("t2", "u2", "T2", BrowserTabRole.comparison)
        reg.close("t1")
        assert reg.count_open() == 1
        assert reg.count() == 2   # all() still includes closed


class TestAttach:
    def test_attach_mission(self):
        reg = _reg()
        reg.register("t1", "u", "t", BrowserTabRole.research)
        ok = reg.attach_mission("t1", "m1")
        assert ok is True
        assert reg.get("t1").mission_id == "m1"

    def test_attach_mission_missing_tab(self):
        reg = _reg()
        assert reg.attach_mission("nope", "m1") is False

    def test_attach_task(self):
        reg = _reg()
        reg.register("t1", "u", "t", BrowserTabRole.workflow)
        ok = reg.attach_task("t1", "task1")
        assert ok is True
        assert reg.get("t1").task_id == "task1"

    def test_detach_mission(self):
        reg = _reg()
        reg.register("t1", "u", "t", BrowserTabRole.research, mission_id="m1")
        reg.detach_mission("t1")
        assert reg.get("t1").mission_id is None

    def test_detach_task(self):
        reg = _reg()
        reg.register("t1", "u", "t", BrowserTabRole.research, task_id="task1")
        reg.detach_task("t1")
        assert reg.get("t1").task_id is None


class TestQuery:
    def test_for_mission_filters_correctly(self):
        reg = _reg()
        reg.register("t1", "u1", "T1", BrowserTabRole.research, mission_id="m1")
        reg.register("t2", "u2", "T2", BrowserTabRole.comparison, mission_id="m2")
        result = reg.for_mission("m1")
        assert len(result) == 1
        assert result[0].tab_id == "t1"

    def test_open_for_mission_excludes_closed(self):
        reg = _reg()
        reg.register("t1", "u1", "T1", BrowserTabRole.research, mission_id="m1")
        reg.register("t2", "u2", "T2", BrowserTabRole.comparison, mission_id="m1")
        reg.close("t1")
        open_tabs = reg.open_for_mission("m1")
        assert len(open_tabs) == 1
        assert open_tabs[0].tab_id == "t2"

    def test_for_task(self):
        reg = _reg()
        reg.register("t1", "u", "T", BrowserTabRole.workflow, task_id="task1")
        result = reg.for_task("task1")
        assert len(result) == 1

    def test_all_includes_closed(self):
        reg = _reg()
        reg.register("t1", "u", "T", BrowserTabRole.research)
        reg.close("t1")
        assert len(reg.all()) == 1

    def test_all_open_excludes_closed(self):
        reg = _reg()
        reg.register("t1", "u", "T", BrowserTabRole.research)
        reg.close("t1")
        assert len(reg.all_open()) == 0

    def test_reset_for_testing(self):
        reg = _reg()
        reg.register("t1", "u", "T", BrowserTabRole.research)
        reg._reset_for_testing()
        assert reg.count() == 0
