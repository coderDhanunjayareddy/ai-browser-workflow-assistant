"""Phase D — Unit tests: monitor.py (ExecutionMonitor)."""
import pytest
from app.execution_gateway.browser import monitor as mon


@pytest.fixture(autouse=True)
def clean():
    mon._reset_for_testing()
    yield
    mon._reset_for_testing()


class TestStartFinish:
    def test_start_step(self):
        rec = mon.start_step("e1", "s1", 1, "click", 100.0)
        assert rec.execution_id == "e1"
        assert rec.step_id == "s1"
        assert rec.finished_at is None

    def test_finish_step(self):
        rec = mon.start_step("e1", "s1", 1, "click", 100.0)
        mon.finish_step(rec, finished_at=100.5, attempts=2, outcome="completed",
                        validation_result=True, locator_strategy="testid",
                        recovery_used=["WAIT"])
        assert rec.outcome == "completed"
        assert rec.attempts == 2
        assert rec.retries == 1
        assert rec.validation_result is True
        assert rec.locator_strategy == "testid"
        assert rec.recovery_used == ["WAIT"]
        assert rec.elapsed_ms == 500.0

    def test_failure_record(self):
        rec = mon.start_step("e1", "s2", 2, "click", 0.0)
        mon.finish_step(rec, finished_at=0.1, attempts=3, outcome="failed",
                        failure_category="ElementNotFound")
        assert rec.outcome == "failed"
        assert rec.failure_category == "ElementNotFound"
        assert rec.retries == 2


class TestQueries:
    def test_steps_for(self):
        mon.start_step("e1", "s1", 1, "navigate", 0.0)
        mon.start_step("e1", "s2", 2, "click", 0.0)
        assert len(mon.steps_for("e1")) == 2

    def test_steps_for_empty(self):
        assert mon.steps_for("absent") == []

    def test_current_step_unfinished(self):
        mon.start_step("e1", "s1", 1, "navigate", 0.0)
        r2 = mon.start_step("e1", "s2", 2, "click", 0.0)
        assert mon.current_step("e1") is r2

    def test_summary(self):
        r1 = mon.start_step("e1", "s1", 1, "navigate", 0.0)
        mon.finish_step(r1, finished_at=0.1, attempts=1, outcome="completed", validation_result=True)
        r2 = mon.start_step("e1", "s2", 2, "click", 0.0)
        mon.finish_step(r2, finished_at=0.2, attempts=2, outcome="failed",
                        failure_category="ElementNotFound", recovery_used=["WAIT"])
        s = mon.summary("e1")
        assert s["total_steps"] == 2
        assert s["completed_steps"] == 1
        assert s["failed_steps"] == 1
        assert s["total_retries"] == 1
        assert s["recoveries_used"] == 1

    def test_record_to_dict(self):
        rec = mon.start_step("e1", "s1", 1, "click", 0.0)
        d = rec.to_dict()
        for k in ["execution_id", "step_id", "order", "phase", "started_at", "finished_at",
                  "elapsed_ms", "attempts", "retries", "validation_result", "failure_category",
                  "recovery_used", "locator_strategy", "screenshots", "outcome"]:
            assert k in d


class TestStats:
    def test_stats(self):
        mon.start_step("e1", "s1", 1, "click", 0.0)
        s = mon.stats()
        assert s["tracked_executions"] == 1
        assert s["tracked_steps"] == 1

    def test_reset(self):
        mon.start_step("e1", "s1", 1, "click", 0.0)
        mon._reset_for_testing()
        assert mon.steps_for("e1") == []
