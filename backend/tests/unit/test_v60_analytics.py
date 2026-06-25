"""
V6.0 Unit Tests — TabAnalytics (14 tests).
"""
import pytest

from app.tabs import analytics as tab_analytics


@pytest.fixture(autouse=True)
def reset():
    tab_analytics._reset_for_testing()
    yield


class TestInitialState:
    def test_all_counters_start_at_zero(self):
        a = tab_analytics.get_analytics()
        for key, val in a.items():
            assert val == 0, f"{key} should start at 0, got {val}"

    def test_active_tabs_starts_at_zero(self):
        a = tab_analytics.get_analytics()
        assert a["active_tabs"] == 0


class TestRecording:
    def test_record_tab_created(self):
        tab_analytics.record_tab_created()
        assert tab_analytics.get_analytics()["tabs_created"] == 1

    def test_record_tab_closed(self):
        tab_analytics.record_tab_created()
        tab_analytics.record_tab_closed()
        a = tab_analytics.get_analytics()
        assert a["tabs_closed"] == 1
        assert a["active_tabs"] == 0

    def test_active_tabs_computed(self):
        tab_analytics.record_tab_created()
        tab_analytics.record_tab_created()
        tab_analytics.record_tab_closed()
        a = tab_analytics.get_analytics()
        assert a["active_tabs"] == 1

    def test_record_tab_restored(self):
        tab_analytics.record_tab_restored()
        assert tab_analytics.get_analytics()["tabs_restored"] == 1

    def test_record_snapshot(self):
        tab_analytics.record_snapshot()
        tab_analytics.record_snapshot()
        assert tab_analytics.get_analytics()["tab_snapshots"] == 2

    def test_record_mission_link(self):
        tab_analytics.record_mission_link()
        assert tab_analytics.get_analytics()["mission_tab_links"] == 1

    def test_record_task_link(self):
        tab_analytics.record_task_link()
        assert tab_analytics.get_analytics()["task_tab_links"] == 1

    def test_record_context_build(self):
        tab_analytics.record_context_build(latency_ms=5)
        a = tab_analytics.get_analytics()
        assert a["context_builds"] == 1
        assert a["avg_latency_ms"] == 5

    def test_record_multiple_context_builds_averages(self):
        tab_analytics.record_context_build(latency_ms=10)
        tab_analytics.record_context_build(latency_ms=20)
        a = tab_analytics.get_analytics()
        assert a["avg_latency_ms"] == 15

    def test_record_intelligence_run(self):
        tab_analytics.record_intelligence_run()
        assert tab_analytics.get_analytics()["intelligence_runs"] == 1

    def test_reset_clears_all(self):
        tab_analytics.record_tab_created()
        tab_analytics.record_snapshot()
        tab_analytics.record_mission_link()
        tab_analytics._reset_for_testing()
        a = tab_analytics.get_analytics()
        assert a["tabs_created"]      == 0
        assert a["tab_snapshots"]     == 0
        assert a["mission_tab_links"] == 0

    def test_active_tabs_never_negative(self):
        # More closes than creates
        tab_analytics.record_tab_closed()
        tab_analytics.record_tab_closed()
        a = tab_analytics.get_analytics()
        assert a["active_tabs"] == 0
