"""
V7.0 Unit Tests — BrowserActivityTimeline + BrowserEventAnalytics (20 tests).
"""
import pytest

from app.browser.models import BrowserEventType, make_event
from app.browser import analytics as bra
from app.browser import timeline as tl


@pytest.fixture(autouse=True)
def reset():
    bra._reset_for_testing()
    tl._reset_for_testing()
    yield
    bra._reset_for_testing()
    tl._reset_for_testing()


def _ev(tab_id="t1", et=BrowserEventType.tab_created, mission_id=None):
    return make_event(et, tab_id, mission_id=mission_id, url="https://x.com")


# ── BrowserActivityTimeline ───────────────────────────────────────────────────

class TestBrowserActivityTimeline:
    def test_append_and_get(self):
        ev = _ev(mission_id="m1")
        tl.append("m1", ev)
        events = tl.get("m1")
        assert len(events) == 1
        assert events[0]["event_id"] == ev.event_id

    def test_newest_first(self):
        e1 = _ev("t1", mission_id="m1")
        e2 = _ev("t2", mission_id="m1")
        tl.append("m1", e1)
        tl.append("m1", e2)
        events = tl.get("m1")
        assert events[0]["event_id"] == e2.event_id  # newest first

    def test_limit_respected(self):
        for i in range(10):
            tl.append("m1", _ev(f"t{i}", mission_id="m1"))
        assert len(tl.get("m1", limit=3)) == 3

    def test_different_missions_isolated(self):
        tl.append("m1", _ev("t1", mission_id="m1"))
        tl.append("m2", _ev("t2", mission_id="m2"))
        assert len(tl.get("m1")) == 1
        assert len(tl.get("m2")) == 1

    def test_empty_mission_returns_empty(self):
        assert tl.get("no-mission") == []

    def test_summary_counts(self):
        tl.append("m1", _ev("t1", BrowserEventType.tab_created,  mission_id="m1"))
        tl.append("m1", _ev("t2", BrowserEventType.url_changed,  mission_id="m1"))
        tl.append("m1", _ev("t3", BrowserEventType.url_changed,  mission_id="m1"))
        s = tl.summary("m1")
        assert s["event_count"]                  == 3
        assert s["type_counts"]["TAB_CREATED"]   == 1
        assert s["type_counts"]["URL_CHANGED"]   == 2

    def test_summary_latest_event(self):
        ev = _ev(mission_id="m1")
        tl.append("m1", ev)
        s = tl.summary("m1")
        assert s["latest_event"] is not None
        assert s["latest_event"]["event_id"] == ev.event_id

    def test_summary_empty_mission(self):
        s = tl.summary("nobody")
        assert s["event_count"] == 0
        assert s["latest_event"] is None

    def test_global_append(self):
        ev = _ev()  # no mission_id
        tl.append_global(ev)
        recent = tl.recent_global(limit=5)
        assert any(e["event_id"] == ev.event_id for e in recent)

    def test_missions_with_activity(self):
        tl.append("m-A", _ev("t1", mission_id="m-A"))
        tl.append("m-B", _ev("t2", mission_id="m-B"))
        active = tl.missions_with_activity()
        assert "m-A" in active
        assert "m-B" in active

    def test_reset_clears(self):
        tl.append("m1", _ev(mission_id="m1"))
        tl._reset_for_testing()
        assert tl.get("m1") == []


# ── BrowserEventAnalytics ─────────────────────────────────────────────────────

class TestBrowserEventAnalytics:
    def test_initial_zeros(self):
        a = bra.get_analytics()
        assert a["events_received"]          == 0
        assert a["mission_refreshes"]        == 0
        assert a["recommendation_refreshes"] == 0

    def test_record_tab_created(self):
        bra.record_event(BrowserEventType.tab_created)
        a = bra.get_analytics()
        assert a["events_received"] == 1
        assert a["tab_created"]     == 1

    def test_record_url_changed(self):
        bra.record_event(BrowserEventType.url_changed)
        a = bra.get_analytics()
        assert a["url_changed"] == 1

    def test_record_all_event_types(self):
        for et in BrowserEventType:
            bra.record_event(et)
        a = bra.get_analytics()
        assert a["events_received"] == len(BrowserEventType)

    def test_record_mission_refresh(self):
        bra.record_mission_refresh()
        bra.record_mission_refresh()
        a = bra.get_analytics()
        assert a["mission_refreshes"] == 2

    def test_record_trust_refresh(self):
        bra.record_trust_refresh()
        a = bra.get_analytics()
        assert a["trust_refreshes"] == 1

    def test_record_recommendation_refresh(self):
        bra.record_recommendation_refresh()
        bra.record_recommendation_refresh()
        bra.record_recommendation_refresh()
        a = bra.get_analytics()
        assert a["recommendation_refreshes"] == 3

    def test_reset_clears(self):
        bra.record_event(BrowserEventType.tab_created)
        bra._reset_for_testing()
        a = bra.get_analytics()
        assert a["events_received"] == 0
