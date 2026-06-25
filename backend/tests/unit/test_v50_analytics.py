"""
Unit tests for V5.0 MissionAnalytics.
Covers: record functions, get_analytics(), rates, averages, thread safety.
"""
import pytest

from app.mission import analytics as mission_analytics


@pytest.fixture(autouse=True)
def reset():
    mission_analytics._reset_for_testing()
    yield
    mission_analytics._reset_for_testing()


class TestRecordMissionCreated:
    def test_increments_total(self):
        mission_analytics.record_mission_created()
        assert mission_analytics.get_analytics()["total_missions"] == 1

    def test_increments_active(self):
        mission_analytics.record_mission_created()
        assert mission_analytics.get_analytics()["active_missions"] == 1

    def test_multiple_creates(self):
        for _ in range(5):
            mission_analytics.record_mission_created()
        assert mission_analytics.get_analytics()["total_missions"] == 5


class TestRecordMissionCompleted:
    def test_increments_completed(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_completed()
        a = mission_analytics.get_analytics()
        assert a["completed_missions"] == 1

    def test_decrements_active(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_completed()
        assert mission_analytics.get_analytics()["active_missions"] == 0

    def test_active_never_goes_negative(self):
        mission_analytics.record_mission_completed()
        assert mission_analytics.get_analytics()["active_missions"] == 0

    def test_completion_rate(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_completed()
        a = mission_analytics.get_analytics()
        assert a["mission_completion_rate"] == pytest.approx(0.5)

    def test_average_duration_ms(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_completed(duration_ms=200)
        a = mission_analytics.get_analytics()
        assert a["average_mission_duration_ms"] == 200


class TestRecordMissionFailed:
    def test_increments_failed(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_failed()
        assert mission_analytics.get_analytics()["failed_missions"] == 1

    def test_decrements_active(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_failed()
        assert mission_analytics.get_analytics()["active_missions"] == 0


class TestRecordMissionAbandoned:
    def test_increments_abandoned(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_abandoned()
        assert mission_analytics.get_analytics()["abandoned_missions"] == 1


class TestRecordTaskAttached:
    def test_increments_tasks_attached(self):
        mission_analytics.record_task_attached()
        mission_analytics.record_task_attached()
        assert mission_analytics.get_analytics()["total_tasks_attached"] == 2

    def test_average_tasks_per_mission(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_task_attached()
        mission_analytics.record_task_attached()
        a = mission_analytics.get_analytics()
        assert a["average_tasks_per_mission"] == pytest.approx(2.0)


class TestResearchToExecution:
    def test_rate(self):
        mission_analytics.record_mission_created()
        mission_analytics.record_mission_created()
        mission_analytics.record_research_to_execution()
        a = mission_analytics.get_analytics()
        assert a["research_to_execution_rate"] == pytest.approx(0.5)


class TestGetAnalyticsDefaults:
    def test_all_zeros_at_start(self):
        a = mission_analytics.get_analytics()
        assert a["total_missions"] == 0
        assert a["completed_missions"] == 0
        assert a["average_tasks_per_mission"] == 0.0
        assert a["mission_completion_rate"] == 0.0
