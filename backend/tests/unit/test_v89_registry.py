"""V8.9 Browser Runtime Layer — Unit tests: registry.py (RuntimeSessionRegistry)."""
import time
import pytest
from app.runtime import registry as reg
from app.runtime.registry import RuntimeSessionRegistry
from app.runtime.models import make_session, RuntimeState


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


def _sess(rid="rt-1", mission="m-1", now=None):
    return make_session(runtime_id=rid, active_mission_id=mission,
                        active_tab_id="tab-1", now=now or time.time())


class TestAddGet:
    def test_add_then_get(self):
        reg.add(_sess())
        assert reg.get("rt-1") is not None

    def test_get_missing_none(self):
        assert reg.get("absent") is None

    def test_count(self):
        reg.add(_sess(rid="rt-1")); reg.add(_sess(rid="rt-2"))
        assert reg.count() == 2

    def test_list_all(self):
        reg.add(_sess(rid="rt-1")); reg.add(_sess(rid="rt-2"))
        assert len(reg.list_all()) == 2

    def test_list_all_limit(self):
        for i in range(5):
            reg.add(_sess(rid=f"rt-{i}"))
        assert len(reg.list_all(limit=2)) == 2


class TestMissionIndex:
    def test_list_for_mission(self):
        reg.add(_sess(rid="rt-1", mission="m-A"))
        reg.add(_sess(rid="rt-2", mission="m-A"))
        reg.add(_sess(rid="rt-3", mission="m-B"))
        assert len(reg.list_for_mission("m-A")) == 2

    def test_list_for_mission_empty(self):
        assert reg.list_for_mission("absent") == []

    def test_summary_for_mission(self):
        reg.add(_sess(rid="rt-1", mission="m-A"))
        s = reg.summary_for_mission("m-A")
        assert s["total_sessions"] == 1
        assert "active_tab_id" in s
        assert "runtime_ids" in s

    def test_summary_empty_mission(self):
        s = reg.summary_for_mission("absent")
        assert s["total_sessions"] == 0


class TestUpdate:
    def test_touch_updates(self):
        reg.add(_sess())
        assert reg.touch("rt-1", wall_now=time.time() + 10) is True

    def test_touch_missing_false(self):
        assert reg.touch("absent", wall_now=time.time()) is False

    def test_update_session_tab(self):
        reg.add(_sess())
        reg.update_session("rt-1", wall_now=time.time(), active_tab_id="tab-99")
        assert reg.get("rt-1").active_tab_id == "tab-99"

    def test_update_session_state(self):
        reg.add(_sess())
        reg.update_session("rt-1", wall_now=time.time(), runtime_state=RuntimeState.active)
        assert reg.get("rt-1").runtime_state == RuntimeState.active

    def test_update_missing_none(self):
        assert reg.update_session("absent", wall_now=time.time()) is None

    def test_update_reindexes_mission(self):
        reg.add(_sess(rid="rt-1", mission="m-A"))
        reg.update_session("rt-1", wall_now=time.time(), active_mission_id="m-B")
        assert len(reg.list_for_mission("m-A")) == 0
        assert len(reg.list_for_mission("m-B")) == 1

    def test_set_state(self):
        reg.add(_sess())
        assert reg.set_state("rt-1", RuntimeState.stale) is True
        assert reg.get("rt-1").runtime_state == RuntimeState.stale

    def test_set_state_missing_false(self):
        assert reg.set_state("absent", RuntimeState.stale) is False


class TestStateCounts:
    def test_count_by_state(self):
        reg.add(_sess(rid="rt-1"))
        reg.update_session("rt-1", wall_now=time.time(), runtime_state=RuntimeState.active)
        reg.add(_sess(rid="rt-2"))  # idle
        assert reg.count_by_state(RuntimeState.active) == 1
        assert reg.count_by_state(RuntimeState.idle) == 1


class TestTTL:
    def test_session_expires(self):
        r = RuntimeSessionRegistry(ttl=0.05)
        r.add(make_session(runtime_id="rt-1", now=time.time()))
        time.sleep(0.08)
        assert r.get("rt-1") is None

    def test_expired_not_in_count(self):
        r = RuntimeSessionRegistry(ttl=0.05)
        r.add(make_session(runtime_id="rt-1", now=time.time()))
        time.sleep(0.08)
        assert r.count() == 0


class TestStats:
    def test_stats_keys(self):
        s = reg.stats()
        for k in ["cached_sessions", "total_added", "total_evicted", "mission_keys", "ttl_seconds"]:
            assert k in s

    def test_total_added(self):
        reg.add(_sess(rid="rt-1")); reg.add(_sess(rid="rt-2"))
        assert reg.stats()["total_added"] == 2

    def test_reset_clears(self):
        reg.add(_sess())
        reg._reset_for_testing()
        assert reg.count() == 0
