"""Phase B Execution Gateway — Unit tests: analytics.py."""
import pytest
from app.execution_gateway import analytics as anal


@pytest.fixture(autouse=True)
def clean():
    anal._reset_for_testing()
    yield
    anal._reset_for_testing()


class TestInitial:
    def test_zeros(self):
        a = anal.get_analytics()
        for k in ["executions_started", "executions_completed", "executions_failed",
                  "executions_aborted", "steps_executed", "total_retries", "rollbacks_performed"]:
            assert a[k] == 0

    def test_keys(self):
        a = anal.get_analytics()
        for k in ["executions_started", "executions_completed", "executions_failed",
                  "executions_aborted", "steps_executed", "steps_failed", "total_retries",
                  "rollbacks_performed", "total_duration_ms", "avg_steps_per_execution",
                  "avg_duration_ms", "success_rate"]:
            assert k in a


class TestStarted:
    def test_started_increments(self):
        anal.record_started()
        assert anal.get_analytics()["executions_started"] == 1


class TestFinished:
    def test_completed(self):
        anal.record_finished(state="COMPLETED", steps_executed=3, steps_failed=0, retries=0, rollbacks=0, duration_ms=15.0)
        a = anal.get_analytics()
        assert a["executions_completed"] == 1
        assert a["steps_executed"] == 3

    def test_failed(self):
        anal.record_finished(state="FAILED", steps_executed=2, steps_failed=1, retries=1, rollbacks=1, duration_ms=10.0)
        a = anal.get_analytics()
        assert a["executions_failed"] == 1
        assert a["steps_failed"] == 1
        assert a["total_retries"] == 1
        assert a["rollbacks_performed"] == 1

    def test_aborted(self):
        anal.record_finished(state="ABORTED", steps_executed=1, steps_failed=0, retries=0, rollbacks=1, duration_ms=5.0)
        assert anal.get_analytics()["executions_aborted"] == 1

    def test_avg_steps(self):
        anal.record_finished(state="COMPLETED", steps_executed=2, steps_failed=0, retries=0, rollbacks=0, duration_ms=10.0)
        anal.record_finished(state="COMPLETED", steps_executed=4, steps_failed=0, retries=0, rollbacks=0, duration_ms=20.0)
        assert anal.get_analytics()["avg_steps_per_execution"] == 3.0

    def test_avg_duration(self):
        anal.record_finished(state="COMPLETED", steps_executed=2, steps_failed=0, retries=0, rollbacks=0, duration_ms=10.0)
        anal.record_finished(state="COMPLETED", steps_executed=2, steps_failed=0, retries=0, rollbacks=0, duration_ms=20.0)
        assert anal.get_analytics()["avg_duration_ms"] == 15.0

    def test_success_rate(self):
        anal.record_finished(state="COMPLETED", steps_executed=2, steps_failed=0, retries=0, rollbacks=0, duration_ms=10.0)
        anal.record_finished(state="FAILED", steps_executed=1, steps_failed=1, retries=0, rollbacks=1, duration_ms=5.0)
        assert anal.get_analytics()["success_rate"] == 0.5

    def test_total_duration(self):
        anal.record_finished(state="COMPLETED", steps_executed=2, steps_failed=0, retries=0, rollbacks=0, duration_ms=12.5)
        assert anal.get_analytics()["total_duration_ms"] == 12.5


class TestReset:
    def test_reset(self):
        anal.record_started()
        anal.record_finished(state="COMPLETED", steps_executed=3, steps_failed=0, retries=0, rollbacks=0, duration_ms=10.0)
        anal._reset_for_testing()
        a = anal.get_analytics()
        assert a["executions_started"] == 0
        assert a["executions_completed"] == 0
        assert a["avg_steps_per_execution"] == 0.0
