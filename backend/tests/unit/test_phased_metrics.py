"""Phase D — Unit tests: metrics.py (ExecutionMetrics)."""
import pytest
from app.execution_gateway.browser import metrics as met


@pytest.fixture(autouse=True)
def clean():
    met._reset_for_testing()
    yield
    met._reset_for_testing()


class TestInitial:
    def test_zeros(self):
        m = met.get_metrics()
        for k in ["steps_total", "steps_succeeded", "steps_failed", "retries_total",
                  "recoveries_attempted", "recoveries_succeeded", "validations_attempted",
                  "validations_passed"]:
            assert m.get(k, 0) == 0 or k not in m or m[k] == 0

    def test_keys(self):
        m = met.get_metrics()
        for k in ["steps_total", "step_success_rate", "average_retries", "average_execution_ms",
                  "recoveries_attempted", "recovery_success_rate", "validations_attempted",
                  "validation_success_rate", "locator_strategy_counts", "locator_strategy_pct",
                  "failure_distribution"]:
            assert k in m


class TestRecordStep:
    def test_success(self):
        met.record_step(succeeded=True, retries=0, elapsed_ms=10.0, locator_strategy="testid")
        m = met.get_metrics()
        assert m["steps_total"] == 1
        assert m["steps_succeeded"] == 1
        assert m["step_success_rate"] == 1.0

    def test_average_retries(self):
        met.record_step(succeeded=True, retries=1, elapsed_ms=10.0)
        met.record_step(succeeded=True, retries=3, elapsed_ms=10.0)
        assert met.get_metrics()["average_retries"] == 2.0

    def test_average_time(self):
        met.record_step(succeeded=True, retries=0, elapsed_ms=10.0)
        met.record_step(succeeded=True, retries=0, elapsed_ms=20.0)
        assert met.get_metrics()["average_execution_ms"] == 15.0

    def test_step_success_rate(self):
        met.record_step(succeeded=True, retries=0, elapsed_ms=10.0)
        met.record_step(succeeded=False, retries=0, elapsed_ms=10.0)
        assert met.get_metrics()["step_success_rate"] == 0.5

    def test_locator_strategy_distribution(self):
        met.record_step(succeeded=True, retries=0, elapsed_ms=1.0, locator_strategy="testid")
        met.record_step(succeeded=True, retries=0, elapsed_ms=1.0, locator_strategy="testid")
        met.record_step(succeeded=True, retries=0, elapsed_ms=1.0, locator_strategy="css")
        m = met.get_metrics()
        assert m["locator_strategy_counts"]["testid"] == 2
        assert m["locator_strategy_pct"]["testid"] == round(2 / 3, 4)


class TestRecovery:
    def test_recovery_success_rate(self):
        met.record_recovery(succeeded=True)
        met.record_recovery(succeeded=True)
        met.record_recovery(succeeded=False)
        assert met.get_metrics()["recovery_success_rate"] == round(2 / 3, 4)


class TestValidation:
    def test_validation_success_rate(self):
        met.record_validation(passed=True)
        met.record_validation(passed=False)
        assert met.get_metrics()["validation_success_rate"] == 0.5


class TestFailureDistribution:
    def test_failure_distribution(self):
        met.record_failure("ElementNotFound")
        met.record_failure("ElementNotFound")
        met.record_failure("NavigationTimeout")
        d = met.get_metrics()["failure_distribution"]
        assert d["ElementNotFound"] == 2
        assert d["NavigationTimeout"] == 1


class TestReset:
    def test_reset(self):
        met.record_step(succeeded=True, retries=0, elapsed_ms=1.0)
        met.record_failure("X")
        met._reset_for_testing()
        m = met.get_metrics()
        assert m["steps_total"] == 0
        assert m["failure_distribution"] == {}
