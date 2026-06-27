"""V8.9 Browser Runtime Layer — Unit tests: cache.py (ContextCache)."""
import time
import pytest
from app.runtime import cache
from app.runtime.cache import ContextCache
from app.runtime.models import ContextSnapshot


@pytest.fixture(autouse=True)
def clean():
    cache._reset_for_testing()
    yield
    cache._reset_for_testing()


def _snap(url="http://a.com", title="A"):
    return ContextSnapshot(last_url=url, last_title=title, cached_at=time.time())


class TestSetGet:
    def test_set_then_get(self):
        cache.set("rt-1", _snap())
        assert cache.get("rt-1") is not None

    def test_get_returns_snapshot(self):
        cache.set("rt-1", _snap(url="http://x"))
        assert cache.get("rt-1").last_url == "http://x"

    def test_get_missing_none(self):
        assert cache.get("nope") is None

    def test_overwrite(self):
        cache.set("rt-1", _snap(url="http://a"))
        cache.set("rt-1", _snap(url="http://b"))
        assert cache.get("rt-1").last_url == "http://b"

    def test_count(self):
        cache.set("rt-1", _snap()); cache.set("rt-2", _snap())
        assert cache.count() == 2


class TestHitMiss:
    def test_hit_counted(self):
        cache.set("rt-1", _snap())
        cache.get("rt-1")
        assert cache.stats()["cache_hits"] == 1

    def test_miss_counted(self):
        cache.get("absent")
        assert cache.stats()["cache_misses"] == 1

    def test_hit_ratio(self):
        cache.set("rt-1", _snap())
        cache.get("rt-1")   # hit
        cache.get("absent") # miss
        assert cache.stats()["hit_ratio"] == 0.5

    def test_peek_no_hit_count(self):
        cache.set("rt-1", _snap())
        cache.peek("rt-1")
        assert cache.stats()["cache_hits"] == 0

    def test_zero_ratio_when_empty(self):
        assert cache.stats()["hit_ratio"] == 0.0


class TestFreshness:
    def test_is_fresh_after_set(self):
        cache.set("rt-1", _snap())
        assert cache.is_fresh("rt-1")

    def test_not_fresh_missing(self):
        assert not cache.is_fresh("absent")

    def test_age_seconds_set(self):
        cache.set("rt-1", _snap())
        age = cache.age_seconds("rt-1")
        assert age is not None and age >= 0.0

    def test_age_seconds_missing(self):
        assert cache.age_seconds("absent") is None


class TestTTL:
    def test_short_ttl_expires(self):
        c = ContextCache(ttl=0.05)
        c.set("rt-1", _snap())
        time.sleep(0.08)
        assert c.get("rt-1") is None

    def test_expiry_counts_miss(self):
        c = ContextCache(ttl=0.05)
        c.set("rt-1", _snap())
        time.sleep(0.08)
        c.get("rt-1")
        assert c.stats()["cache_misses"] == 1

    def test_not_fresh_after_ttl(self):
        c = ContextCache(ttl=0.05)
        c.set("rt-1", _snap())
        time.sleep(0.08)
        assert not c.is_fresh("rt-1")


class TestInvalidate:
    def test_invalidate_removes(self):
        cache.set("rt-1", _snap())
        assert cache.invalidate("rt-1") is True
        assert cache.get("rt-1") is None

    def test_invalidate_missing_false(self):
        assert cache.invalidate("absent") is False


class TestStats:
    def test_stats_keys(self):
        s = cache.stats()
        for k in ["cached_runtimes", "cache_hits", "cache_misses", "hit_ratio", "ttl_seconds"]:
            assert k in s

    def test_default_ttl_300(self):
        assert cache.stats()["ttl_seconds"] == 300.0

    def test_reset_clears(self):
        cache.set("rt-1", _snap())
        cache._reset_for_testing()
        assert cache.count() == 0
        assert cache.stats()["cache_hits"] == 0
