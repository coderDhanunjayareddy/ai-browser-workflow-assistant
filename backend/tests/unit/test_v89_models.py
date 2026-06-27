"""V8.9 Browser Runtime Layer — Unit tests: models.py."""
import pytest
from app.runtime.models import (
    RuntimeState, RuntimeEventType, PrefetchType, ALL_RUNTIME_EVENT_TYPES,
    RuntimeSession, ContextSnapshot, ContextDiff, RuntimeEvent, PrefetchHint,
    RuntimeContext, CONTEXT_FIELDS,
    make_session, make_runtime_event,
)


class TestRuntimeState:
    def test_idle(self):    assert RuntimeState.idle.value    == "IDLE"
    def test_active(self):  assert RuntimeState.active.value  == "ACTIVE"
    def test_syncing(self): assert RuntimeState.syncing.value == "SYNCING"
    def test_stale(self):   assert RuntimeState.stale.value   == "STALE"
    def test_from_string(self): assert RuntimeState("ACTIVE") == RuntimeState.active
    def test_count(self):   assert len(RuntimeState) == 4


class TestRuntimeEventType:
    def test_page_changed(self):      assert RuntimeEventType.page_changed.value      == "PAGE_CHANGED"
    def test_url_changed(self):       assert RuntimeEventType.url_changed.value       == "URL_CHANGED"
    def test_selection_changed(self): assert RuntimeEventType.selection_changed.value == "SELECTION_CHANGED"
    def test_dom_updated(self):       assert RuntimeEventType.dom_updated.value       == "DOM_UPDATED"
    def test_tab_switched(self):      assert RuntimeEventType.tab_switched.value      == "TAB_SWITCHED"
    def test_mission_switched(self):  assert RuntimeEventType.mission_switched.value  == "MISSION_SWITCHED"
    def test_task_switched(self):     assert RuntimeEventType.task_switched.value     == "TASK_SWITCHED"
    def test_seven_types(self):       assert len(RuntimeEventType) == 7
    def test_all_tuple(self):         assert len(ALL_RUNTIME_EVENT_TYPES) == 7


class TestPrefetchType:
    def test_none(self):      assert PrefetchType.none.value      == "NONE"
    def test_summarize(self): assert PrefetchType.summarize.value == "SUMMARIZE"
    def test_qa(self):        assert PrefetchType.qa.value        == "QA"
    def test_compare(self):   assert PrefetchType.compare.value   == "COMPARE"
    def test_count(self):     assert len(PrefetchType) == 4


class TestRuntimeSession:
    def test_make_generates_id(self):
        s = make_session(now=100.0)
        assert s.runtime_id.startswith("rt-")

    def test_make_uses_given_id(self):
        s = make_session(runtime_id="rt-fixed", now=1.0)
        assert s.runtime_id == "rt-fixed"

    def test_initial_state_idle(self):
        assert make_session(now=1.0).runtime_state == RuntimeState.idle

    def test_created_updated_set(self):
        s = make_session(now=42.0)
        assert s.created_at == 42.0 and s.updated_at == 42.0

    def test_fields_stored(self):
        s = make_session(runtime_id="r", browser_window_id="w1", active_tab_id="t1",
                         active_mission_id="m1", active_task_id="tk1", now=1.0)
        assert s.browser_window_id == "w1"
        assert s.active_tab_id == "t1"
        assert s.active_mission_id == "m1"
        assert s.active_task_id == "tk1"

    def test_to_dict_keys(self):
        d = make_session(now=1.0).to_dict()
        for k in ["runtime_id", "browser_window_id", "active_tab_id",
                  "active_mission_id", "active_task_id", "runtime_state",
                  "created_at", "updated_at"]:
            assert k in d

    def test_to_dict_state_is_string(self):
        assert make_session(now=1.0).to_dict()["runtime_state"] == "IDLE"

    def test_unique_ids(self):
        assert make_session(now=1.0).runtime_id != make_session(now=1.0).runtime_id


class TestContextSnapshot:
    def test_defaults_none(self):
        s = ContextSnapshot()
        assert s.last_url is None and s.last_title is None

    def test_field_value(self):
        s = ContextSnapshot(last_url="http://x")
        assert s.field_value("last_url") == "http://x"

    def test_field_value_missing(self):
        assert ContextSnapshot().field_value("nope") is None

    def test_context_fields_count(self):
        assert len(CONTEXT_FIELDS) == 6

    def test_to_dict_keys(self):
        d = ContextSnapshot(last_url="u", last_title="t").to_dict()
        for k in CONTEXT_FIELDS:
            assert k in d
        assert "cached_at" in d and "dom_mutation_count" in d


class TestContextDiff:
    def test_empty_no_changes(self):
        d = ContextDiff()
        assert not d.has_changes
        assert d.changed_field_count == 0
        assert d.diff_ratio == 0.0

    def test_added_counts(self):
        d = ContextDiff(added={"last_url": "u"})
        assert d.changed_field_count == 1
        assert d.has_changes

    def test_combined_count(self):
        d = ContextDiff(added={"a": 1}, removed={"b": 2}, modified={"c": 3})
        assert d.changed_field_count == 3

    def test_diff_ratio(self):
        d = ContextDiff(modified={"last_url": "u", "last_title": "t", "last_selection": "s"})
        assert d.diff_ratio == round(3 / 6, 4)

    def test_to_dict_keys(self):
        d = ContextDiff(added={"x": 1}).to_dict()
        for k in ["added", "removed", "modified", "changed_field_count", "has_changes", "diff_ratio"]:
            assert k in d


class TestRuntimeEvent:
    def test_make_generates_id(self):
        e = make_runtime_event(RuntimeEventType.page_changed, "rt-1", now=1.0)
        assert e.event_id.startswith("re-")

    def test_type_stored(self):
        e = make_runtime_event(RuntimeEventType.url_changed, "rt-1", now=1.0)
        assert e.event_type == RuntimeEventType.url_changed

    def test_runtime_id_stored(self):
        assert make_runtime_event(RuntimeEventType.dom_updated, "rt-x", now=1.0).runtime_id == "rt-x"

    def test_detail_stored(self):
        e = make_runtime_event(RuntimeEventType.url_changed, "rt", now=1.0, detail={"to": "u"})
        assert e.detail == {"to": "u"}

    def test_to_dict_keys(self):
        d = make_runtime_event(RuntimeEventType.tab_switched, "rt", now=1.0).to_dict()
        for k in ["event_id", "event_type", "runtime_id", "timestamp", "mission_id", "task_id", "tab_id", "detail"]:
            assert k in d

    def test_to_dict_type_is_string(self):
        assert make_runtime_event(RuntimeEventType.page_changed, "rt", now=1.0).to_dict()["event_type"] == "PAGE_CHANGED"


class TestPrefetchHint:
    def test_none_not_actionable(self):
        h = PrefetchHint(prefetch_type=PrefetchType.none, reason="x")
        assert not h.is_actionable

    def test_summarize_actionable(self):
        h = PrefetchHint(prefetch_type=PrefetchType.summarize, reason="x")
        assert h.is_actionable

    def test_to_dict_keys(self):
        d = PrefetchHint(prefetch_type=PrefetchType.qa, reason="r", confidence=0.7).to_dict()
        for k in ["prefetch_type", "reason", "confidence", "is_actionable", "signals"]:
            assert k in d

    def test_to_dict_type_is_string(self):
        assert PrefetchHint(prefetch_type=PrefetchType.compare, reason="r").to_dict()["prefetch_type"] == "COMPARE"


class TestRuntimeContext:
    def test_defaults(self):
        c = RuntimeContext(runtime_id="rt-1")
        assert c.execution_ready is False
        assert c.active_mission_id is None

    def test_to_dict_keys(self):
        d = RuntimeContext(runtime_id="rt-1").to_dict()
        for k in ["runtime_id", "active_mission_id", "active_task_id", "mission_state",
                  "approval_state", "authorization_state", "execution_ready", "evaluated_at"]:
            assert k in d
