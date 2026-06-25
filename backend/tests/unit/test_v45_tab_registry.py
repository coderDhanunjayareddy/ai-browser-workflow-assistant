"""
V4.5 Unit Tests — TaskTabRegistry.

Tests cover:
  - register() creates TaskTab
  - register() updates existing tab when same tab_id
  - get_by_role() filter
  - get_all() returns all tabs
  - get() by tab_id
  - summary() returns serializable list
"""
import pytest

from app.unified import store as task_store
from app.unified.models import UnifiedTask, TabRole
from app.unified.tab_registry import TaskTabRegistry


def setup_function():
    task_store._reset_for_testing()


def _task():
    t = UnifiedTask(task_id="t1", conversation_id="c1")
    task_store.put(t)
    return t


@pytest.fixture
def reg():
    return TaskTabRegistry()


class TestRegister:
    def test_creates_tab(self, reg):
        task = _task()
        tab = reg.register(task, "tab1", "https://example.com", "Example", TabRole.research)
        assert tab.tab_id == "tab1"
        assert len(task.tabs) == 1

    def test_updates_existing_tab(self, reg):
        task = _task()
        reg.register(task, "tab1", "https://a.com", "A", TabRole.research)
        reg.register(task, "tab1", "https://b.com", "B", TabRole.workflow)
        assert len(task.tabs) == 1
        assert task.tabs[0].url == "https://b.com"
        assert task.tabs[0].role == TabRole.workflow

    def test_multiple_tabs_added(self, reg):
        task = _task()
        reg.register(task, "tab1", "https://a.com", "A", TabRole.research)
        reg.register(task, "tab2", "https://b.com", "B", TabRole.workflow)
        assert len(task.tabs) == 2

    def test_tab_role_stored(self, reg):
        task = _task()
        tab = reg.register(task, "tab1", "https://x.com", "X", TabRole.approval)
        assert tab.role == TabRole.approval


class TestGetByRole:
    def test_filters_by_role(self, reg):
        task = _task()
        reg.register(task, "t1", "u1", "T1", TabRole.research)
        reg.register(task, "t2", "u2", "T2", TabRole.workflow)
        reg.register(task, "t3", "u3", "T3", TabRole.research)
        research_tabs = reg.get_by_role(task, TabRole.research)
        assert len(research_tabs) == 2

    def test_returns_empty_when_no_match(self, reg):
        task = _task()
        reg.register(task, "t1", "u1", "T1", TabRole.research)
        result = reg.get_by_role(task, TabRole.approval)
        assert result == []


class TestGetAll:
    def test_returns_all_tabs(self, reg):
        task = _task()
        for i in range(3):
            reg.register(task, f"tab{i}", f"https://e{i}.com", f"E{i}", TabRole.reference)
        assert len(reg.get_all(task)) == 3


class TestGet:
    def test_finds_by_tab_id(self, reg):
        task = _task()
        reg.register(task, "mytab", "https://x.com", "X", TabRole.workflow)
        found = reg.get(task, "mytab")
        assert found is not None
        assert found.url == "https://x.com"

    def test_returns_none_for_unknown(self, reg):
        task = _task()
        assert reg.get(task, "unknown") is None


class TestSummary:
    def test_returns_list_of_dicts(self, reg):
        task = _task()
        reg.register(task, "t1", "https://a.com", "A", TabRole.research)
        s = reg.summary(task)
        assert isinstance(s, list)
        assert len(s) == 1
        assert "tab_id" in s[0]
        assert "role" in s[0]
        assert s[0]["role"] == "RESEARCH"
