"""V9.0 Execution Planning Layer — Unit tests: analytics.py."""
import pytest
from app.execution_planning import analytics as anal


@pytest.fixture(autouse=True)
def clean():
    anal._reset_for_testing()
    yield
    anal._reset_for_testing()


class TestInitial:
    def test_zeros(self):
        a = anal.get_analytics()
        for k in ["plans_created", "plans_validated", "validation_failures",
                  "rollback_supported", "archived"]:
            assert a[k] == 0

    def test_avgs_zero(self):
        a = anal.get_analytics()
        assert a["avg_steps"] == 0.0
        assert a["avg_duration_ms"] == 0.0

    def test_keys(self):
        a = anal.get_analytics()
        for k in ["plans_created", "plans_validated", "validation_failures",
                  "avg_steps", "avg_duration_ms", "rollback_supported", "archived"]:
            assert k in a


class TestRecordCreated:
    def test_created_increments(self):
        anal.record_created(3, 1450, True)
        assert anal.get_analytics()["plans_created"] == 1

    def test_rollback_supported_counted(self):
        anal.record_created(3, 1450, True)
        anal.record_created(2, 800, False)
        assert anal.get_analytics()["rollback_supported"] == 1

    def test_avg_steps(self):
        anal.record_created(2, 800, True)
        anal.record_created(4, 1600, True)
        assert anal.get_analytics()["avg_steps"] == 3.0

    def test_avg_duration(self):
        anal.record_created(2, 800, True)
        anal.record_created(2, 1200, True)
        assert anal.get_analytics()["avg_duration_ms"] == 1000.0


class TestRecordValidated:
    def test_validated_pass(self):
        anal.record_validated(True)
        assert anal.get_analytics()["plans_validated"] == 1
        assert anal.get_analytics()["validation_failures"] == 0

    def test_validated_fail(self):
        anal.record_validated(False)
        assert anal.get_analytics()["validation_failures"] == 1
        assert anal.get_analytics()["plans_validated"] == 0

    def test_mixed(self):
        anal.record_validated(True)
        anal.record_validated(True)
        anal.record_validated(False)
        a = anal.get_analytics()
        assert a["plans_validated"] == 2
        assert a["validation_failures"] == 1


class TestArchived:
    def test_archived_counted(self):
        anal.record_archived()
        anal.record_archived()
        assert anal.get_analytics()["archived"] == 2


class TestReset:
    def test_reset_clears(self):
        anal.record_created(3, 1450, True)
        anal.record_validated(True)
        anal.record_archived()
        anal._reset_for_testing()
        a = anal.get_analytics()
        assert a["plans_created"] == 0
        assert a["plans_validated"] == 0
        assert a["archived"] == 0
        assert a["avg_steps"] == 0.0
