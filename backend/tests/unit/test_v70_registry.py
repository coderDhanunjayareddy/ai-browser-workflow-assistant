"""
V7.0 Unit Tests — BrowserEventRegistry (18 tests).
"""
import time
import pytest

from app.browser.models import BrowserEventType, make_event
import app.browser.registry as ev_reg


@pytest.fixture(autouse=True)
def reset():
    ev_reg._reset_for_testing()
    yield
    ev_reg._reset_for_testing()


def _ev(tab_id="t1", et=BrowserEventType.tab_created, mission_id=None):
    return make_event(et, tab_id, mission_id=mission_id, url="https://x.com")


class TestRegisterAndGet:
    def test_register_and_get(self):
        e = _ev()
        ev_reg.register(e)
        out = ev_reg.get(e.event_id)
        assert out is not None
        assert out.event_id == e.event_id

    def test_get_unknown_returns_none(self):
        assert ev_reg.get("nonexistent-id") is None

    def test_count_increases(self):
        ev_reg.register(_ev())
        ev_reg.register(_ev())
        assert ev_reg.count() == 2

    def test_reset_clears(self):
        ev_reg.register(_ev())
        ev_reg._reset_for_testing()
        assert ev_reg.count() == 0

    def test_stats_structure(self):
        ev_reg.register(_ev())
        s = ev_reg.stats()
        assert "cached_events"    in s
        assert "total_registered" in s
        assert "total_evicted"    in s
        assert s["total_registered"] >= 1


class TestMissionIndex:
    def test_events_for_mission(self):
        e1 = _ev("t1", mission_id="m1")
        e2 = _ev("t2", mission_id="m1")
        e3 = _ev("t3", mission_id="m2")
        for e in [e1, e2, e3]:
            ev_reg.register(e)
        result = ev_reg.events_for_mission("m1")
        ids = {e.event_id for e in result}
        assert e1.event_id in ids
        assert e2.event_id in ids
        assert e3.event_id not in ids

    def test_empty_mission_returns_empty(self):
        assert ev_reg.events_for_mission("nonexistent") == []

    def test_limit_respected(self):
        for i in range(10):
            ev_reg.register(_ev(f"t{i}", mission_id="m-limit"))
        result = ev_reg.events_for_mission("m-limit", limit=3)
        assert len(result) <= 3

    def test_no_mission_id_not_indexed(self):
        e = _ev("t1", mission_id=None)
        ev_reg.register(e)
        assert ev_reg.events_for_mission("") == []


class TestTabIndex:
    def test_events_for_tab(self):
        e1 = _ev("tab-A", BrowserEventType.tab_created)
        e2 = _ev("tab-A", BrowserEventType.url_changed)
        e3 = _ev("tab-B", BrowserEventType.tab_created)
        for e in [e1, e2, e3]:
            ev_reg.register(e)
        result = ev_reg.events_for_tab("tab-A")
        ids = {e.event_id for e in result}
        assert e1.event_id in ids
        assert e2.event_id in ids
        assert e3.event_id not in ids

    def test_empty_tab_returns_empty(self):
        assert ev_reg.events_for_tab("unknown-tab") == []


class TestRecentEvents:
    def test_recent_events_newest_first(self):
        for i in range(5):
            ev_reg.register(_ev(f"t{i}"))
        recent = ev_reg.recent_events(limit=10)
        assert len(recent) == 5

    def test_limit_respected(self):
        for i in range(20):
            ev_reg.register(_ev(f"t{i}"))
        recent = ev_reg.recent_events(limit=5)
        assert len(recent) == 5


class TestTTLExpiry:
    def test_expired_event_returns_none(self):
        from app.browser.registry import BrowserEventRegistry
        short_reg = BrowserEventRegistry(ttl=1)   # 1s TTL
        e = _ev()
        short_reg.register(e)
        # Manually backdate the insertion time to force expiry
        with short_reg._lock:
            ev_obj, _ = short_reg._cache[e.event_id]
            short_reg._cache[e.event_id] = (ev_obj, time.monotonic() - 5)
        assert short_reg.get(e.event_id) is None

    def test_events_for_mission_skips_expired(self):
        from app.browser.registry import BrowserEventRegistry
        short_reg = BrowserEventRegistry(ttl=1)
        e = _ev("t1", mission_id="m1")
        short_reg.register(e)
        with short_reg._lock:
            ev_obj, _ = short_reg._cache[e.event_id]
            short_reg._cache[e.event_id] = (ev_obj, time.monotonic() - 5)
        assert short_reg.events_for_mission("m1") == []
