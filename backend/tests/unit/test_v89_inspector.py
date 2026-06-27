"""V8.9 Browser Runtime Layer — Unit tests: inspector.py (RuntimeInspector)."""
import pytest
from app.runtime import inspector as insp
from app.runtime import sync_service, registry, cache, events, analytics


@pytest.fixture(autouse=True)
def clean():
    registry._reset_for_testing()
    cache._reset_for_testing()
    events._reset_for_testing()
    analytics._reset_for_testing()
    yield
    registry._reset_for_testing()
    cache._reset_for_testing()
    events._reset_for_testing()
    analytics._reset_for_testing()


def _synced(mission="m-1"):
    return sync_service.sync(active_mission_id=mission, active_tab_id="tab-1",
                             last_url="http://a", last_title="A",
                             last_read_view="x" * 100).runtime_id


class TestStructure:
    def test_returns_dict(self):
        rid = _synced()
        assert isinstance(insp.inspect(rid), dict)

    def test_has_runtime_id(self):
        rid = _synced()
        assert insp.inspect(rid)["runtime_id"] == rid

    def test_has_session(self):
        rid = _synced()
        assert insp.inspect(rid)["session"] is not None

    def test_has_cache_health(self):
        rid = _synced()
        assert "cache_health" in insp.inspect(rid)

    def test_has_context_freshness(self):
        rid = _synced()
        assert "context_freshness" in insp.inspect(rid)

    def test_has_event_summary(self):
        rid = _synced()
        assert "event_summary" in insp.inspect(rid)

    def test_has_prefetch(self):
        rid = _synced()
        assert "prefetch" in insp.inspect(rid)

    def test_has_runtime_context(self):
        rid = _synced()
        assert "runtime_context" in insp.inspect(rid)

    def test_has_authorization_runtime(self):
        rid = _synced()
        assert "authorization_runtime" in insp.inspect(rid)

    def test_has_analytics(self):
        rid = _synced()
        assert "analytics" in insp.inspect(rid)

    def test_has_stats_blocks(self):
        rid = _synced()
        r = insp.inspect(rid)
        assert "registry_stats" in r
        assert "cache_stats" in r
        assert "queue_stats" in r

    def test_has_latency(self):
        rid = _synced()
        assert insp.inspect(rid)["latency_ms"] >= 0.0


class TestCacheHealth:
    def test_has_context_true(self):
        rid = _synced()
        assert insp.inspect(rid)["cache_health"]["has_context"] is True

    def test_is_fresh(self):
        rid = _synced()
        assert insp.inspect(rid)["cache_health"]["is_fresh"] is True

    def test_context_summary_has_url(self):
        rid = _synced()
        summary = insp.inspect(rid)["cache_health"]["context_summary"]
        assert summary["last_url"] == "http://a"


class TestFreshness:
    def test_freshness_label_present(self):
        rid = _synced()
        assert "label" in insp.inspect(rid)["context_freshness"]

    def test_freshness_live_or_fresh(self):
        rid = _synced()
        assert insp.inspect(rid)["context_freshness"]["label"] in ("live", "fresh", "aging")


class TestAuthorizationRuntime:
    def test_execution_ready_present(self):
        rid = _synced()
        ar = insp.inspect(rid)["authorization_runtime"]
        assert "execution_ready" in ar

    def test_execution_ready_false_without_auth(self):
        rid = _synced()
        # no authorization issued → not execution_ready
        assert insp.inspect(rid)["authorization_runtime"]["execution_ready"] is False


class TestEmptyRuntime:
    def test_missing_runtime_no_session(self):
        r = insp.inspect("rt-absent")
        assert r["session"] is None

    def test_missing_runtime_no_context(self):
        r = insp.inspect("rt-absent")
        assert r["cache_health"]["has_context"] is False
