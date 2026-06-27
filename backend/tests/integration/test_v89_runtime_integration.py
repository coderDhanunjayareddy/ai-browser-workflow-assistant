"""
V8.9 Browser Runtime Layer — Integration tests.

Exercises the /runtime REST API plus cross-layer integration with the
V7.0 browser sync, V5.0 mission inspector, and V8.8 authorization layers.
All state flows through the same singleton registries the app uses.
"""
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runtime import registry as rt_reg
from app.runtime import cache as rt_cache
from app.runtime import events as rt_events
from app.runtime import analytics as rt_anal

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean():
    rt_reg._reset_for_testing()
    rt_cache._reset_for_testing()
    rt_events._reset_for_testing()
    rt_anal._reset_for_testing()
    yield
    rt_reg._reset_for_testing()
    rt_cache._reset_for_testing()
    rt_events._reset_for_testing()
    rt_anal._reset_for_testing()


def _sync(**body):
    return client.post("/runtime/sync", json=body)


# ── POST /runtime/sync ────────────────────────────────────────────────────────

class TestSyncEndpoint:

    def test_sync_200(self):
        r = _sync(last_url="http://a", last_title="A")
        assert r.status_code == 200

    def test_sync_returns_runtime_id(self):
        r = _sync(last_url="http://a")
        assert r.json()["runtime_id"].startswith("rt-")

    def test_sync_created_true_first(self):
        r = _sync(last_url="http://a")
        assert r.json()["created"] is True

    def test_sync_cache_miss_first(self):
        r = _sync(last_url="http://a")
        assert r.json()["cache_hit"] is False

    def test_sync_reuse_runtime(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        r2 = _sync(runtime_id=rid, last_url="http://b")
        assert r2.json()["created"] is False
        assert r2.json()["cache_hit"] is True

    def test_sync_returns_diff(self):
        r = _sync(last_url="http://a", last_title="A")
        assert r.json()["diff"]["has_changes"] is True

    def test_sync_returns_events(self):
        r = _sync(last_url="http://a")
        types = [e["event_type"] for e in r.json()["events"]]
        assert "URL_CHANGED" in types

    def test_sync_returns_prefetch(self):
        r = _sync(last_url="http://a")
        assert "prefetch_type" in r.json()["prefetch"]

    def test_sync_returns_context(self):
        r = _sync(active_mission_id="m-1", last_url="http://a")
        assert r.json()["context"]["active_mission_id"] == "m-1"

    def test_sync_url_change_diff(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        r2 = _sync(runtime_id=rid, last_url="http://b")
        assert "last_url" in r2.json()["diff"]["modified"]


# ── GET /runtime ──────────────────────────────────────────────────────────────

class TestListEndpoint:

    def test_empty_initially(self):
        r = client.get("/runtime")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_after_sync(self):
        _sync(last_url="http://a")
        r = client.get("/runtime")
        assert len(r.json()) == 1

    def test_filter_by_mission(self):
        _sync(active_mission_id="m-A", last_url="http://a")
        _sync(active_mission_id="m-B", last_url="http://b")
        r = client.get("/runtime?mission_id=m-A")
        assert len(r.json()) == 1

    def test_filter_by_state_active(self):
        _sync(last_url="http://a")
        r = client.get("/runtime?state=ACTIVE")
        assert len(r.json()) == 1

    def test_filter_invalid_state_400(self):
        r = client.get("/runtime?state=BOGUS")
        assert r.status_code == 400


# ── GET /runtime/context ──────────────────────────────────────────────────────

class TestContextEndpoint:

    def test_context_200(self):
        rid = _sync(active_mission_id="m-1", last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/context?runtime_id={rid}")
        assert r.status_code == 200

    def test_context_mission_id(self):
        rid = _sync(active_mission_id="m-1", last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/context?runtime_id={rid}")
        assert r.json()["active_mission_id"] == "m-1"

    def test_context_has_execution_ready(self):
        rid = _sync(active_mission_id="m-1", last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/context?runtime_id={rid}")
        assert "execution_ready" in r.json()

    def test_context_missing_404(self):
        r = client.get("/runtime/context?runtime_id=rt-absent")
        assert r.status_code == 404


# ── GET /runtime/events ───────────────────────────────────────────────────────

class TestEventsEndpoint:

    def test_events_empty(self):
        r = client.get("/runtime/events")
        assert r.status_code == 200
        assert r.json() == []

    def test_events_after_sync(self):
        rid = _sync(last_url="http://a", last_title="A").json()["runtime_id"]
        r = client.get(f"/runtime/events?runtime_id={rid}")
        assert len(r.json()) >= 1

    def test_events_global(self):
        _sync(last_url="http://a")
        r = client.get("/runtime/events")
        assert len(r.json()) >= 1

    def test_events_limit(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        for i in range(5):
            _sync(runtime_id=rid, last_url=f"http://{i}")
        r = client.get(f"/runtime/events?runtime_id={rid}&limit=2")
        assert len(r.json()) == 2


# ── GET /runtime/cache ────────────────────────────────────────────────────────

class TestCacheEndpoint:

    def test_cache_200(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/cache?runtime_id={rid}")
        assert r.status_code == 200

    def test_cache_has_snapshot(self):
        rid = _sync(last_url="http://a", last_title="A").json()["runtime_id"]
        r = client.get(f"/runtime/cache?runtime_id={rid}")
        assert r.json()["snapshot"]["last_url"] == "http://a"

    def test_cache_fresh(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/cache?runtime_id={rid}")
        assert r.json()["is_fresh"] is True

    def test_cache_missing_404(self):
        r = client.get("/runtime/cache?runtime_id=rt-absent")
        assert r.status_code == 404


# ── GET /runtime/analytics ────────────────────────────────────────────────────

class TestAnalyticsEndpoint:

    def test_analytics_200(self):
        r = client.get("/runtime/analytics")
        assert r.status_code == 200

    def test_analytics_keys(self):
        r = client.get("/runtime/analytics")
        for k in ["runtime_uptime_seconds", "syncs", "cache_hits", "cache_misses",
                  "cache_hit_ratio", "avg_context_diff_ratio",
                  "prefetch_opportunities", "event_rate"]:
            assert k in r.json()

    def test_analytics_syncs_increment(self):
        _sync(last_url="http://a")
        _sync(last_url="http://b")
        assert client.get("/runtime/analytics").json()["syncs"] == 2

    def test_analytics_cache_hit_recorded(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        _sync(runtime_id=rid, last_url="http://b")
        assert client.get("/runtime/analytics").json()["cache_hits"] >= 1


# ── GET /runtime/inspect ──────────────────────────────────────────────────────

class TestInspectEndpoint:

    def test_inspect_200(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/inspect?runtime_id={rid}")
        assert r.status_code == 200

    def test_inspect_keys(self):
        rid = _sync(last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/inspect?runtime_id={rid}")
        for k in ["runtime_id", "session", "cache_health", "context_freshness",
                  "event_summary", "prefetch", "runtime_context",
                  "authorization_runtime", "analytics", "latency_ms"]:
            assert k in r.json()

    def test_inspect_missing_404(self):
        r = client.get("/runtime/inspect?runtime_id=rt-absent")
        assert r.status_code == 404


# ── Browser sync integration (V7.0) ───────────────────────────────────────────

class TestBrowserSyncIntegration:

    def test_inspect_links_browser_events(self):
        from app.browser import registry as browser_reg
        from app.browser.models import make_event, BrowserEventType
        browser_reg._reset_for_testing()
        ev = make_event(BrowserEventType.page_loaded, "tab-1",
                        url="http://a", title="A", mission_id="m-bsync")
        browser_reg.register(ev)
        rid = _sync(active_mission_id="m-bsync", active_tab_id="tab-1", last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/inspect?runtime_id={rid}")
        bs = r.json()["browser_sync"]
        assert bs is not None
        assert bs["linked_mission"] == "m-bsync"
        browser_reg._reset_for_testing()

    def test_runtime_does_not_duplicate_browser_events(self):
        # Runtime events and browser events live in separate registries.
        from app.browser import registry as browser_reg
        browser_reg._reset_for_testing()
        _sync(active_mission_id="m-x", last_url="http://a")
        # browser registry untouched by a runtime sync
        assert browser_reg.count() == 0


# ── Mission runtime integration (V5.0 inspector) ──────────────────────────────

class TestMissionRuntimeIntegration:

    def test_mission_inspect_has_runtime_key(self):
        from app.mission import store as ms
        from app.mission.models import Mission, MissionState
        m = Mission("m-rt-insp", "Runtime Test", "test", MissionState.active)
        ms.put(m)
        r = client.get("/mission/m-rt-insp/inspect")
        assert r.status_code == 200
        assert "runtime" in r.json()

    def test_mission_inspect_runtime_populated(self):
        from app.mission import store as ms
        from app.mission.models import Mission, MissionState
        m = Mission("m-rt-pop", "Runtime Pop", "test", MissionState.active)
        ms.put(m)
        _sync(active_mission_id="m-rt-pop", active_tab_id="tab-9", last_url="http://a")
        r = client.get("/mission/m-rt-pop/inspect")
        runtime = r.json()["runtime"]
        assert runtime is not None
        assert runtime["runtime_health"]["total_sessions"] >= 1
        assert runtime["active_tab_id"] == "tab-9"


# ── Authorization runtime integration (V8.8, read-only) ───────────────────────

class TestAuthorizationRuntimeIntegration:

    def test_execution_ready_false_without_authorization(self):
        rid = _sync(active_mission_id="m-noauth", last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/context?runtime_id={rid}")
        assert r.json()["execution_ready"] is False

    def test_execution_ready_true_with_executable_auth(self):
        # Create governance contract → evaluate authorization → runtime reads it
        from app.governance import registry as gov_reg
        from app.governance.models import make_contract
        from app.authorization import registry as auth_reg
        gov_reg._reset_for_testing()
        auth_reg._reset_for_testing()
        c = make_contract(str(uuid.uuid4()), True, "tester", time.time(),
                          "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
                          mission_id="m-auth-rt", task_id="t-1", ttl_seconds=3600)
        gov_reg.add(c)
        ev = client.post(f"/authorization/evaluate/{c.contract_id}")
        assert ev.status_code == 200
        assert ev.json()["authorized"] is True
        rid = _sync(active_mission_id="m-auth-rt", last_url="http://a").json()["runtime_id"]
        r = client.get(f"/runtime/context?runtime_id={rid}")
        assert r.json()["execution_ready"] is True
        assert r.json()["authorization_state"]["active_authorizations"] >= 1
        gov_reg._reset_for_testing()
        auth_reg._reset_for_testing()

    def test_runtime_never_mutates_authorization(self):
        # Syncing the runtime must not create/alter any authorization.
        from app.authorization import registry as auth_reg
        auth_reg._reset_for_testing()
        _sync(active_mission_id="m-readonly", last_url="http://a")
        assert auth_reg.count() == 0
