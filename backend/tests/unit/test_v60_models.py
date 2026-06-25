"""
V6.0 Unit Tests — Domain Models (20 tests).
"""
import pytest
from datetime import datetime

from app.tabs.models import (
    BrowserTab, BrowserTabRole, BrowserTabState,
    TabSyncPayload, create_tab,
    TERMINAL_TAB_STATES, ACTIVE_TAB_STATES,
)


class TestBrowserTabRole:
    def test_all_roles_defined(self):
        roles = {r.value for r in BrowserTabRole}
        assert roles == {"PRIMARY", "RESEARCH", "COMPARISON", "WORKFLOW", "REFERENCE"}

    def test_role_string_values(self):
        assert BrowserTabRole.primary.value    == "PRIMARY"
        assert BrowserTabRole.research.value   == "RESEARCH"
        assert BrowserTabRole.comparison.value == "COMPARISON"
        assert BrowserTabRole.workflow.value   == "WORKFLOW"
        assert BrowserTabRole.reference.value  == "REFERENCE"

    def test_role_from_string(self):
        assert BrowserTabRole("RESEARCH") == BrowserTabRole.research


class TestBrowserTabState:
    def test_all_states_defined(self):
        states = {s.value for s in BrowserTabState}
        assert states == {"OPEN", "ACTIVE", "BACKGROUND", "CLOSED"}

    def test_terminal_states(self):
        assert BrowserTabState.closed in TERMINAL_TAB_STATES
        assert BrowserTabState.open not in TERMINAL_TAB_STATES

    def test_active_states_exclude_closed(self):
        assert BrowserTabState.closed not in ACTIVE_TAB_STATES
        for s in (BrowserTabState.open, BrowserTabState.active, BrowserTabState.background):
            assert s in ACTIVE_TAB_STATES


class TestBrowserTab:
    def test_create_tab_factory(self):
        tab = create_tab("https://example.com", "Example", BrowserTabRole.research)
        assert tab.url   == "https://example.com"
        assert tab.title == "Example"
        assert tab.role  == BrowserTabRole.research
        assert tab.state == BrowserTabState.open
        assert tab.tab_id

    def test_explicit_tab_id(self):
        tab = create_tab("https://a.com", "A", BrowserTabRole.primary, tab_id="custom-id")
        assert tab.tab_id == "custom-id"

    def test_is_active_open(self):
        tab = create_tab("u", "t", BrowserTabRole.reference, state=BrowserTabState.open)
        assert tab.is_active is True

    def test_is_active_background(self):
        tab = create_tab("u", "t", BrowserTabRole.reference, state=BrowserTabState.background)
        assert tab.is_active is True

    def test_is_active_closed(self):
        tab = create_tab("u", "t", BrowserTabRole.reference, state=BrowserTabState.closed)
        assert tab.is_active is False

    def test_is_closed(self):
        tab = create_tab("u", "t", BrowserTabRole.reference, state=BrowserTabState.closed)
        assert tab.is_closed is True

    def test_touch_updates_timestamp(self):
        tab = create_tab("u", "t", BrowserTabRole.research)
        before = tab.updated_at
        tab.touch()
        assert tab.updated_at >= before

    def test_to_summary_keys(self):
        tab = create_tab("https://x.com", "X", BrowserTabRole.comparison,
                         mission_id="m1", task_id="t1")
        s = tab.to_summary()
        assert s["tab_id"]     == tab.tab_id
        assert s["url"]        == "https://x.com"
        assert s["role"]       == "COMPARISON"
        assert s["mission_id"] == "m1"
        assert s["task_id"]    == "t1"
        assert "created_at" in s
        assert "updated_at" in s

    def test_optional_mission_task_none_by_default(self):
        tab = create_tab("u", "t", BrowserTabRole.workflow)
        assert tab.mission_id is None
        assert tab.task_id    is None

    def test_timestamps_are_datetimes(self):
        tab = create_tab("u", "t", BrowserTabRole.primary)
        assert isinstance(tab.created_at, datetime)
        assert isinstance(tab.updated_at, datetime)


class TestTabSyncPayload:
    def test_defaults(self):
        p = TabSyncPayload(tab_id="t1", url="https://x.com", title="X")
        assert p.active     is False
        assert p.mission_id is None
        assert p.task_id    is None

    def test_to_dict(self):
        p = TabSyncPayload(tab_id="t1", url="https://x.com", title="X",
                           active=True, mission_id="m1")
        d = p.to_dict()
        assert d["tab_id"]     == "t1"
        assert d["url"]        == "https://x.com"
        assert d["active"]     is True
        assert d["mission_id"] == "m1"
        assert "timestamp" in d

    def test_payload_is_extension_contract_only(self):
        # Payload does NOT trigger any Chrome API calls — it's just a data class
        p = TabSyncPayload(tab_id="t1", url="u", title="t")
        assert isinstance(p.to_dict(), dict)
