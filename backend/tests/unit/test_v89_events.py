"""V8.9 Browser Runtime Layer — Unit tests: events.py (RuntimeEventQueue)."""
import pytest
from app.runtime import events as eq
from app.runtime.events import RuntimeEventQueue, QUEUE_LIMIT
from app.runtime.models import make_runtime_event, RuntimeEventType


@pytest.fixture(autouse=True)
def clean():
    eq._reset_for_testing()
    yield
    eq._reset_for_testing()


def _ev(rt="rt-1", et=RuntimeEventType.page_changed, now=1.0):
    return make_runtime_event(et, rt, now=now)


class TestEnqueue:
    def test_enqueue_increments_count(self):
        eq.enqueue(_ev())
        assert eq.count() == 1

    def test_enqueue_many(self):
        n = eq.enqueue_many([_ev(), _ev(), _ev()])
        assert n == 3
        assert eq.count() == 3

    def test_total_enqueued_stat(self):
        eq.enqueue(_ev()); eq.enqueue(_ev())
        assert eq.stats()["total_enqueued"] == 2


class TestRetrieval:
    def test_get_for_runtime(self):
        eq.enqueue(_ev(rt="rt-A"))
        eq.enqueue(_ev(rt="rt-B"))
        assert len(eq.get_for_runtime("rt-A")) == 1

    def test_newest_first(self):
        eq.enqueue(_ev(rt="rt-1", et=RuntimeEventType.page_changed))
        eq.enqueue(_ev(rt="rt-1", et=RuntimeEventType.url_changed))
        evs = eq.get_for_runtime("rt-1")
        assert evs[0].event_type == RuntimeEventType.url_changed

    def test_recent_global(self):
        eq.enqueue(_ev(rt="rt-1")); eq.enqueue(_ev(rt="rt-2"))
        assert len(eq.recent_global()) == 2

    def test_limit_respected(self):
        for _ in range(10):
            eq.enqueue(_ev(rt="rt-1"))
        assert len(eq.get_for_runtime("rt-1", limit=3)) == 3

    def test_count_for_runtime(self):
        eq.enqueue(_ev(rt="rt-1")); eq.enqueue(_ev(rt="rt-1"))
        eq.enqueue(_ev(rt="rt-2"))
        assert eq.count_for_runtime("rt-1") == 2

    def test_empty_runtime_returns_empty(self):
        assert eq.get_for_runtime("absent") == []


class TestSummary:
    def test_summary_event_count(self):
        eq.enqueue(_ev(rt="rt-1")); eq.enqueue(_ev(rt="rt-1"))
        assert eq.summary("rt-1")["event_count"] == 2

    def test_summary_type_counts(self):
        eq.enqueue(_ev(rt="rt-1", et=RuntimeEventType.url_changed))
        eq.enqueue(_ev(rt="rt-1", et=RuntimeEventType.url_changed))
        eq.enqueue(_ev(rt="rt-1", et=RuntimeEventType.page_changed))
        counts = eq.summary("rt-1")["type_counts"]
        assert counts["URL_CHANGED"] == 2
        assert counts["PAGE_CHANGED"] == 1

    def test_summary_latest_event(self):
        eq.enqueue(_ev(rt="rt-1", et=RuntimeEventType.tab_switched))
        assert eq.summary("rt-1")["latest_event"]["event_type"] == "TAB_SWITCHED"

    def test_summary_empty(self):
        s = eq.summary("absent")
        assert s["event_count"] == 0
        assert s["latest_event"] is None

    def test_runtimes_with_events(self):
        eq.enqueue(_ev(rt="rt-A"))
        assert "rt-A" in eq.runtimes_with_events()


class TestQueueLimit:
    def test_global_capped_at_limit(self):
        q = RuntimeEventQueue(limit=5)
        for i in range(10):
            q.enqueue(_ev(rt="rt-1", now=float(i)))
        assert q.count() == 5

    def test_default_limit_500(self):
        assert eq.stats()["queue_limit"] == QUEUE_LIMIT

    def test_per_runtime_capped(self):
        # MAX_PER_RUNTIME = 200
        for i in range(250):
            eq.enqueue(_ev(rt="rt-1", now=float(i)))
        assert eq.count_for_runtime("rt-1") <= 200


class TestStats:
    def test_stats_keys(self):
        s = eq.stats()
        for k in ["queued_global", "total_enqueued", "runtime_keys", "queue_limit"]:
            assert k in s

    def test_reset_clears(self):
        eq.enqueue(_ev())
        eq._reset_for_testing()
        assert eq.count() == 0
        assert eq.stats()["total_enqueued"] == 0
