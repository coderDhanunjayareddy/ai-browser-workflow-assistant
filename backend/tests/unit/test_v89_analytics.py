"""V8.9 Browser Runtime Layer — Unit tests: analytics.py (RuntimeAnalytics)."""
import pytest
from app.runtime import analytics as anal


@pytest.fixture(autouse=True)
def clean():
    anal._reset_for_testing()
    yield
    anal._reset_for_testing()


class TestInitial:
    def test_initial_zeros(self):
        a = anal.get_analytics()
        for k in ["syncs", "cached_requests", "cache_hits", "cache_misses",
                  "prefetch_opportunities", "total_events"]:
            assert a[k] == 0

    def test_initial_uptime_zero(self):
        assert anal.get_analytics()["runtime_uptime_seconds"] == 0.0

    def test_initial_ratios_zero(self):
        a = anal.get_analytics()
        assert a["cache_hit_ratio"] == 0.0
        assert a["avg_context_diff_ratio"] == 0.0
        assert a["event_rate"] == 0.0


class TestRecordSync:
    def test_sync_increments(self):
        anal.record_sync(wall_now=100.0, cache_hit=False, diff_ratio=0.5, event_count=2, prefetch=False)
        assert anal.get_analytics()["syncs"] == 1

    def test_cache_miss_counted(self):
        anal.record_sync(wall_now=100.0, cache_hit=False, diff_ratio=0.0, event_count=0, prefetch=False)
        assert anal.get_analytics()["cache_misses"] == 1

    def test_cache_hit_counted(self):
        anal.record_sync(wall_now=100.0, cache_hit=True, diff_ratio=0.0, event_count=0, prefetch=False)
        a = anal.get_analytics()
        assert a["cache_hits"] == 1
        assert a["cached_requests"] == 1

    def test_hit_ratio(self):
        anal.record_sync(wall_now=1.0, cache_hit=True,  diff_ratio=0.0, event_count=0, prefetch=False)
        anal.record_sync(wall_now=2.0, cache_hit=False, diff_ratio=0.0, event_count=0, prefetch=False)
        assert anal.get_analytics()["cache_hit_ratio"] == 0.5

    def test_avg_diff_ratio(self):
        anal.record_sync(wall_now=1.0, cache_hit=True, diff_ratio=0.2, event_count=0, prefetch=False)
        anal.record_sync(wall_now=2.0, cache_hit=True, diff_ratio=0.4, event_count=0, prefetch=False)
        assert anal.get_analytics()["avg_context_diff_ratio"] == round(0.3, 4)

    def test_total_events(self):
        anal.record_sync(wall_now=1.0, cache_hit=True, diff_ratio=0.0, event_count=3, prefetch=False)
        anal.record_sync(wall_now=2.0, cache_hit=True, diff_ratio=0.0, event_count=2, prefetch=False)
        assert anal.get_analytics()["total_events"] == 5

    def test_event_rate(self):
        anal.record_sync(wall_now=1.0, cache_hit=True, diff_ratio=0.0, event_count=4, prefetch=False)
        anal.record_sync(wall_now=2.0, cache_hit=True, diff_ratio=0.0, event_count=0, prefetch=False)
        assert anal.get_analytics()["event_rate"] == round(4 / 2, 4)

    def test_prefetch_opportunity(self):
        anal.record_sync(wall_now=1.0, cache_hit=True, diff_ratio=0.0, event_count=0, prefetch=True)
        assert anal.get_analytics()["prefetch_opportunities"] == 1

    def test_no_prefetch_not_counted(self):
        anal.record_sync(wall_now=1.0, cache_hit=True, diff_ratio=0.0, event_count=0, prefetch=False)
        assert anal.get_analytics()["prefetch_opportunities"] == 0


class TestUptime:
    def test_uptime_from_first_sync(self):
        anal.record_sync(wall_now=100.0, cache_hit=False, diff_ratio=0.0, event_count=0, prefetch=False)
        anal.record_sync(wall_now=130.0, cache_hit=True,  diff_ratio=0.0, event_count=0, prefetch=False)
        assert anal.get_analytics(wall_now=130.0)["runtime_uptime_seconds"] == 30.0

    def test_uptime_uses_wall_now(self):
        anal.record_sync(wall_now=100.0, cache_hit=False, diff_ratio=0.0, event_count=0, prefetch=False)
        assert anal.get_analytics(wall_now=150.0)["runtime_uptime_seconds"] == 50.0

    def test_uptime_never_negative(self):
        anal.record_sync(wall_now=100.0, cache_hit=False, diff_ratio=0.0, event_count=0, prefetch=False)
        assert anal.get_analytics(wall_now=50.0)["runtime_uptime_seconds"] >= 0.0


class TestReset:
    def test_reset_clears(self):
        anal.record_sync(wall_now=1.0, cache_hit=True, diff_ratio=0.5, event_count=2, prefetch=True)
        anal._reset_for_testing()
        a = anal.get_analytics()
        assert a["syncs"] == 0
        assert a["prefetch_opportunities"] == 0
        assert a["runtime_uptime_seconds"] == 0.0

    def test_analytics_keys(self):
        a = anal.get_analytics()
        for k in ["runtime_uptime_seconds", "syncs", "cached_requests", "cache_hits",
                  "cache_misses", "cache_hit_ratio", "avg_context_diff_ratio",
                  "prefetch_opportunities", "total_events", "event_rate"]:
            assert k in a
