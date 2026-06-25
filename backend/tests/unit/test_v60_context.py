"""
V6.0 Unit Tests — CrossTabContextBuilder (16 tests).
"""
import pytest

from app.tabs.context import CrossTabContextBuilder, build, TabContext
from app.tabs.models import BrowserTabRole, BrowserTabState
from app.tabs import analytics as tab_analytics
import app.tabs.registry as global_reg


@pytest.fixture(autouse=True)
def reset():
    global_reg._reset_for_testing()
    tab_analytics._reset_for_testing()
    yield
    global_reg._reset_for_testing()
    tab_analytics._reset_for_testing()


def _reg(tab_id, role=BrowserTabRole.research, mission_id="m1",
         url=None, state=BrowserTabState.open):
    return global_reg.register(
        tab_id=tab_id,
        url=url or f"https://{tab_id}.com",
        title=tab_id,
        role=role,
        state=state,
        mission_id=mission_id,
    )


class TestEmptyMission:
    def test_empty_mission_returns_context(self):
        ctx = build("m1")
        assert isinstance(ctx, TabContext)
        assert ctx.mission_id == "m1"

    def test_empty_mission_zero_counts(self):
        ctx = build("m1")
        assert ctx.tab_count        == 0
        assert ctx.active_tab_count == 0

    def test_empty_mission_false_flags(self):
        ctx = build("m1")
        assert ctx.workflow_tab_present   is False
        assert ctx.comparison_tab_present is False
        assert ctx.research_tab_present   is False

    def test_empty_mission_no_duplicates(self):
        ctx = build("m1")
        assert ctx.duplicate_urls == []


class TestTabCounting:
    def test_counts_open_tabs(self):
        _reg("t1"); _reg("t2"); _reg("t3")
        ctx = build("m1")
        assert ctx.tab_count == 3

    def test_excludes_closed_tabs(self):
        _reg("t1"); _reg("t2")
        global_reg.close("t1")
        ctx = build("m1")
        assert ctx.tab_count == 1

    def test_active_tab_count(self):
        _reg("t1", state=BrowserTabState.active)
        _reg("t2", state=BrowserTabState.background)
        _reg("t3", state=BrowserTabState.open)
        ctx = build("m1")
        assert ctx.active_tab_count == 1

    def test_excludes_other_missions(self):
        _reg("t1", mission_id="m1")
        _reg("t2", mission_id="m2")
        ctx = build("m1")
        assert ctx.tab_count == 1


class TestRoleFlags:
    def test_research_tab_present(self):
        _reg("t1", role=BrowserTabRole.research)
        ctx = build("m1")
        assert ctx.research_tab_present is True

    def test_workflow_tab_present(self):
        _reg("t1", role=BrowserTabRole.workflow)
        ctx = build("m1")
        assert ctx.workflow_tab_present is True

    def test_comparison_tab_present(self):
        _reg("t1", role=BrowserTabRole.comparison)
        ctx = build("m1")
        assert ctx.comparison_tab_present is True

    def test_roles_present_list(self):
        _reg("t1", role=BrowserTabRole.research)
        _reg("t2", role=BrowserTabRole.comparison)
        ctx = build("m1")
        assert "RESEARCH"   in ctx.roles_present
        assert "COMPARISON" in ctx.roles_present


class TestPrimaryAndActive:
    def test_primary_tab_identified(self):
        _reg("t1", role=BrowserTabRole.research)
        _reg("t2", role=BrowserTabRole.primary)
        ctx = build("m1")
        assert ctx.primary_tab is not None
        assert ctx.primary_tab["tab_id"] == "t2"

    def test_active_tab_identified(self):
        _reg("t1", state=BrowserTabState.active)
        _reg("t2", state=BrowserTabState.background)
        ctx = build("m1")
        assert ctx.active_tab is not None
        assert ctx.active_tab["tab_id"] == "t1"

    def test_no_primary_returns_none(self):
        _reg("t1", role=BrowserTabRole.research)
        ctx = build("m1")
        assert ctx.primary_tab is None


class TestDuplicateUrls:
    def test_detects_duplicate_urls(self):
        _reg("t1", url="https://amazon.com")
        _reg("t2", url="https://amazon.com")
        ctx = build("m1")
        assert "https://amazon.com" in ctx.duplicate_urls

    def test_no_duplicates_when_unique(self):
        _reg("t1", url="https://amazon.com")
        _reg("t2", url="https://flipkart.com")
        ctx = build("m1")
        assert ctx.duplicate_urls == []


class TestToDict:
    def test_to_dict_is_serializable(self):
        _reg("t1")
        ctx = build("m1")
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert d["mission_id"]   == "m1"
        assert d["tab_count"]    == 1
        assert "tab_summaries"   in d
        assert "roles_present"   in d
