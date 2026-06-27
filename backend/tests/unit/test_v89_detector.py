"""V8.9 Browser Runtime Layer — Unit tests: detector.py (DOMChangeDetector)."""
import pytest
from app.runtime import detector
from app.runtime.models import ContextSnapshot, RuntimeEventType


def _snap(**kw):
    return ContextSnapshot(**kw)


def _types(events):
    return [e.event_type for e in events]


class TestContentEvents:
    def test_title_change_page_changed(self):
        old = _snap(last_title="A")
        new = _snap(last_title="B")
        evs = detector.detect("rt-1", old, new, now=1.0)
        assert RuntimeEventType.page_changed in _types(evs)

    def test_url_change_url_changed(self):
        old = _snap(last_url="http://a")
        new = _snap(last_url="http://b")
        evs = detector.detect("rt-1", old, new, now=1.0)
        assert RuntimeEventType.url_changed in _types(evs)

    def test_selection_change(self):
        old = _snap(last_selection="x")
        new = _snap(last_selection="y")
        evs = detector.detect("rt-1", old, new, now=1.0)
        assert RuntimeEventType.selection_changed in _types(evs)

    def test_dom_mutation_emits(self):
        new = _snap(dom_mutation_count=5)
        evs = detector.detect("rt-1", None, new, now=1.0)
        assert RuntimeEventType.dom_updated in _types(evs)

    def test_no_dom_event_when_zero(self):
        new = _snap(dom_mutation_count=0, last_url="http://a")
        evs = detector.detect("rt-1", None, new, now=1.0)
        assert RuntimeEventType.dom_updated not in _types(evs)

    def test_no_title_event_when_same(self):
        old = _snap(last_title="A")
        new = _snap(last_title="A")
        evs = detector.detect("rt-1", old, new, now=1.0)
        assert RuntimeEventType.page_changed not in _types(evs)

    def test_no_url_event_when_same(self):
        old = _snap(last_url="http://a")
        new = _snap(last_url="http://a")
        evs = detector.detect("rt-1", old, new, now=1.0)
        assert RuntimeEventType.url_changed not in _types(evs)


class TestFirstSync:
    def test_first_title_is_page_changed(self):
        new = _snap(last_title="A")
        evs = detector.detect("rt-1", None, new, now=1.0)
        assert RuntimeEventType.page_changed in _types(evs)

    def test_first_url_is_url_changed(self):
        new = _snap(last_url="http://a")
        evs = detector.detect("rt-1", None, new, now=1.0)
        assert RuntimeEventType.url_changed in _types(evs)

    def test_empty_snapshot_no_events(self):
        evs = detector.detect("rt-1", None, _snap(), now=1.0)
        assert evs == []


class TestSessionEvents:
    def test_tab_switched(self):
        evs = detector.detect("rt-1", None, _snap(), now=1.0,
                              tab_id="tab-2", old_tab_id="tab-1")
        assert RuntimeEventType.tab_switched in _types(evs)

    def test_no_tab_event_same(self):
        evs = detector.detect("rt-1", None, _snap(), now=1.0,
                              tab_id="tab-1", old_tab_id="tab-1")
        assert RuntimeEventType.tab_switched not in _types(evs)

    def test_mission_switched(self):
        evs = detector.detect("rt-1", None, _snap(), now=1.0,
                              mission_id="m-2", old_mission_id="m-1")
        assert RuntimeEventType.mission_switched in _types(evs)

    def test_task_switched(self):
        evs = detector.detect("rt-1", None, _snap(), now=1.0,
                              task_id="t-2", old_task_id="t-1")
        assert RuntimeEventType.task_switched in _types(evs)

    def test_no_session_event_when_old_none(self):
        # first-ever tab: old_tab_id None → no switch event
        evs = detector.detect("rt-1", None, _snap(), now=1.0, tab_id="tab-1", old_tab_id=None)
        assert RuntimeEventType.tab_switched not in _types(evs)


class TestEventFields:
    def test_url_detail_has_from_to(self):
        old = _snap(last_url="http://a")
        new = _snap(last_url="http://b")
        evs = detector.detect("rt-1", old, new, now=1.0)
        url_ev = [e for e in evs if e.event_type == RuntimeEventType.url_changed][0]
        assert url_ev.detail["from"] == "http://a"
        assert url_ev.detail["to"] == "http://b"

    def test_runtime_id_on_events(self):
        evs = detector.detect("rt-X", None, _snap(last_url="u"), now=1.0)
        assert all(e.runtime_id == "rt-X" for e in evs)

    def test_timestamp_propagated(self):
        evs = detector.detect("rt-1", None, _snap(last_url="u"), now=99.0)
        assert evs[0].timestamp == 99.0

    def test_mission_id_on_events(self):
        evs = detector.detect("rt-1", None, _snap(last_url="u"), now=1.0, mission_id="m-1")
        assert evs[0].mission_id == "m-1"


class TestMultiple:
    def test_multiple_events_at_once(self):
        old = _snap(last_url="http://a", last_title="A")
        new = _snap(last_url="http://b", last_title="B", dom_mutation_count=3)
        evs = detector.detect("rt-1", old, new, now=1.0)
        types = _types(evs)
        assert RuntimeEventType.page_changed in types
        assert RuntimeEventType.url_changed in types
        assert RuntimeEventType.dom_updated in types
        assert len(evs) == 3
