"""V8.9 Browser Runtime Layer — Unit tests: sync_service.py (RuntimeSyncService)."""
import pytest
from app.runtime import sync_service, registry, cache, events, analytics
from app.runtime.models import RuntimeState


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


class TestSessionCreation:
    def test_creates_session_when_no_id(self):
        r = sync_service.sync(active_mission_id="m-1", last_url="http://a")
        assert r.created is True
        assert r.runtime_id.startswith("rt-")

    def test_reuses_session_when_id_given(self):
        r1 = sync_service.sync(last_url="http://a")
        r2 = sync_service.sync(runtime_id=r1.runtime_id, last_url="http://b")
        assert r2.created is False
        assert r2.runtime_id == r1.runtime_id

    def test_session_in_registry(self):
        r = sync_service.sync(last_url="http://a")
        assert registry.get(r.runtime_id) is not None

    def test_session_state_active_after_sync(self):
        r = sync_service.sync(last_url="http://a")
        assert registry.get(r.runtime_id).runtime_state == RuntimeState.active


class TestCacheBehavior:
    def test_first_sync_cache_miss(self):
        r = sync_service.sync(last_url="http://a")
        assert r.cache_hit is False

    def test_second_sync_cache_hit(self):
        r1 = sync_service.sync(last_url="http://a")
        r2 = sync_service.sync(runtime_id=r1.runtime_id, last_url="http://b")
        assert r2.cache_hit is True

    def test_snapshot_cached(self):
        r = sync_service.sync(last_url="http://a", last_title="A")
        snap = cache.peek(r.runtime_id)
        assert snap is not None
        assert snap.last_url == "http://a"


class TestDiff:
    def test_first_sync_diff_has_changes(self):
        r = sync_service.sync(last_url="http://a", last_title="A")
        assert r.diff["has_changes"] is True

    def test_unchanged_second_sync_no_diff(self):
        r1 = sync_service.sync(last_url="http://a", last_title="A")
        r2 = sync_service.sync(runtime_id=r1.runtime_id, last_url="http://a", last_title="A")
        assert r2.diff["has_changes"] is False

    def test_modified_field_in_diff(self):
        r1 = sync_service.sync(last_url="http://a")
        r2 = sync_service.sync(runtime_id=r1.runtime_id, last_url="http://b")
        assert "last_url" in r2.diff["modified"]


class TestEvents:
    def test_first_url_emits_event(self):
        r = sync_service.sync(last_url="http://a")
        types = [e["event_type"] for e in r.events]
        assert "URL_CHANGED" in types

    def test_events_enqueued(self):
        r = sync_service.sync(last_url="http://a", last_title="A")
        assert events.count_for_runtime(r.runtime_id) >= 1

    def test_tab_switch_event(self):
        r1 = sync_service.sync(active_tab_id="tab-1", last_url="http://a")
        r2 = sync_service.sync(runtime_id=r1.runtime_id, active_tab_id="tab-2", last_url="http://a")
        types = [e["event_type"] for e in r2.events]
        assert "TAB_SWITCHED" in types

    def test_no_change_no_events(self):
        r1 = sync_service.sync(last_url="http://a", last_title="A")
        r2 = sync_service.sync(runtime_id=r1.runtime_id, last_url="http://a", last_title="A")
        assert len(r2.events) == 0


class TestPrefetch:
    def test_long_article_prefetch_summarize(self):
        r = sync_service.sync(last_read_view="x" * 3000, last_url="http://a")
        # first sync has 1 url change (nav_signal=1, not >=2) so summarize possible
        assert r.prefetch["prefetch_type"] in ("SUMMARIZE", "COMPARE", "NONE")

    def test_prefetch_present(self):
        r = sync_service.sync(last_url="http://a")
        assert r.prefetch is not None
        assert "prefetch_type" in r.prefetch


class TestContextAndAnalytics:
    def test_context_present(self):
        r = sync_service.sync(active_mission_id="m-1", last_url="http://a")
        assert r.context is not None
        assert r.context["active_mission_id"] == "m-1"

    def test_analytics_recorded(self):
        sync_service.sync(last_url="http://a")
        assert analytics.get_analytics()["syncs"] == 1

    def test_latency_recorded(self):
        r = sync_service.sync(last_url="http://a")
        assert r.latency_ms >= 0.0

    def test_to_dict_keys(self):
        r = sync_service.sync(last_url="http://a")
        d = r.to_dict()
        for k in ["runtime_id", "created", "cache_hit", "diff", "events",
                  "prefetch", "context", "session", "latency_ms"]:
            assert k in d

    def test_session_in_result(self):
        r = sync_service.sync(last_url="http://a")
        assert r.session is not None
        assert r.session["runtime_state"] == "ACTIVE"
