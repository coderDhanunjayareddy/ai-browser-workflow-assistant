"""
V6.0 Unit Tests — MissionTabMap + TaskTabMap (18 tests).
"""
import pytest

from app.tabs.registry import TabRegistry
from app.tabs.models import BrowserTabRole, BrowserTabState
from app.tabs import analytics as tab_analytics
import app.tabs.registry as global_reg
import app.tabs.mission_tab_map as mtm_module
import app.tabs.task_tab_map as ttm_module
from app.tabs.mission_tab_map import MissionTabMap
from app.tabs.task_tab_map import TaskTabMap


@pytest.fixture(autouse=True)
def reset_registry():
    global_reg._reset_for_testing()
    tab_analytics._reset_for_testing()
    yield
    global_reg._reset_for_testing()
    tab_analytics._reset_for_testing()


def _register(tab_id, role=BrowserTabRole.research, mission_id=None, task_id=None,
              state=BrowserTabState.open):
    return global_reg.register(
        tab_id=tab_id, url=f"https://{tab_id}.com", title=tab_id,
        role=role, state=state, mission_id=mission_id, task_id=task_id,
    )


class TestMissionTabMap:
    def test_attach_links_tab_to_mission(self):
        _register("t1")
        ok = mtm_module.attach("m1", "t1")
        assert ok is True
        tabs = mtm_module.list_open("m1")
        assert any(t.tab_id == "t1" for t in tabs)

    def test_detach_removes_link(self):
        _register("t1", mission_id="m1")
        mtm_module.detach("m1", "t1")
        assert len(mtm_module.list_open("m1")) == 0

    def test_detach_wrong_mission_returns_false(self):
        _register("t1", mission_id="m1")
        result = mtm_module.detach("m2", "t1")
        assert result is False

    def test_list_open_excludes_closed(self):
        _register("t1", mission_id="m1")
        _register("t2", mission_id="m1")
        global_reg.close("t1")
        open_tabs = mtm_module.list_open("m1")
        assert len(open_tabs) == 1
        assert open_tabs[0].tab_id == "t2"

    def test_list_all_includes_closed(self):
        _register("t1", mission_id="m1")
        global_reg.close("t1")
        all_tabs = mtm_module.list_all("m1")
        assert len(all_tabs) == 1

    def test_primary_tab_returns_primary_role(self):
        _register("t1", role=BrowserTabRole.research, mission_id="m1")
        _register("t2", role=BrowserTabRole.primary,  mission_id="m1")
        primary = mtm_module.primary_tab("m1")
        assert primary is not None
        assert primary.tab_id == "t2"

    def test_primary_tab_none_when_missing(self):
        _register("t1", role=BrowserTabRole.research, mission_id="m1")
        assert mtm_module.primary_tab("m1") is None

    def test_active_tab_returns_active_state(self):
        _register("t1", mission_id="m1", state=BrowserTabState.background)
        _register("t2", mission_id="m1", state=BrowserTabState.active)
        active = mtm_module.active_tab("m1")
        assert active is not None
        assert active.tab_id == "t2"

    def test_by_role_filters(self):
        _register("t1", role=BrowserTabRole.research,   mission_id="m1")
        _register("t2", role=BrowserTabRole.comparison, mission_id="m1")
        _register("t3", role=BrowserTabRole.research,   mission_id="m1")
        result = mtm_module.by_role("m1", BrowserTabRole.research)
        assert len(result) == 2

    def test_count_open_tabs(self):
        _register("t1", mission_id="m1")
        _register("t2", mission_id="m1")
        global_reg.close("t1")
        assert mtm_module.count("m1") == 1

    def test_summary_returns_serializable_list(self):
        _register("t1", mission_id="m1")
        s = mtm_module.summary("m1")
        assert isinstance(s, list)
        assert s[0]["tab_id"] == "t1"
        assert "url" in s[0]


class TestTaskTabMap:
    def test_attach_links_tab_to_task(self):
        _register("t1")
        ok = ttm_module.attach("task1", "t1")
        assert ok is True
        tabs = ttm_module.list_open("task1")
        assert any(t.tab_id == "t1" for t in tabs)

    def test_detach_removes_task_link(self):
        _register("t1", task_id="task1")
        ttm_module.detach("task1", "t1")
        assert len(ttm_module.list_open("task1")) == 0

    def test_detach_wrong_task_returns_false(self):
        _register("t1", task_id="task1")
        result = ttm_module.detach("task2", "t1")
        assert result is False

    def test_list_open_for_task(self):
        _register("t1", task_id="task1")
        _register("t2", task_id="task1")
        _register("t3", task_id="task2")
        result = ttm_module.list_open("task1")
        assert len(result) == 2

    def test_by_role_for_task(self):
        _register("t1", role=BrowserTabRole.workflow,  task_id="task1")
        _register("t2", role=BrowserTabRole.research,  task_id="task1")
        result = ttm_module.by_role("task1", BrowserTabRole.workflow)
        assert len(result) == 1
        assert result[0].tab_id == "t1"

    def test_count_for_task(self):
        _register("t1", task_id="task1")
        _register("t2", task_id="task1")
        assert ttm_module.count("task1") == 2

    def test_summary_for_task(self):
        _register("t1", task_id="task1")
        s = ttm_module.summary("task1")
        assert isinstance(s, list)
        assert s[0]["task_id"] == "task1"
