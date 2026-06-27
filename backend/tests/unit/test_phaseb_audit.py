"""Phase B Execution Gateway — Unit tests: audit.py."""
import pytest
from app.execution_gateway import audit
from app.execution_gateway.models import make_audit_entry


@pytest.fixture(autouse=True)
def clean():
    audit._reset_for_testing()
    yield
    audit._reset_for_testing()


def _entry(execution_id="exec-1", step_id="step-1", order=1, outcome="SUCCESS"):
    return make_audit_entry(execution_id, step_id, order, "NAVIGATE", 100.0, 5.0, outcome, True, 0)


class TestAppend:
    def test_append(self):
        audit.append(_entry())
        assert audit.count_for_execution("exec-1") == 1

    def test_total(self):
        audit.append(_entry()); audit.append(_entry())
        assert audit.total() == 2

    def test_chronological(self):
        audit.append(_entry(order=1))
        audit.append(_entry(order=2))
        entries = audit.entries_for_execution("exec-1")
        assert entries[0].order == 1
        assert entries[1].order == 2

    def test_per_execution_isolation(self):
        audit.append(_entry(execution_id="exec-A"))
        audit.append(_entry(execution_id="exec-B"))
        assert audit.count_for_execution("exec-A") == 1
        assert audit.count_for_execution("exec-B") == 1

    def test_empty_execution(self):
        assert audit.entries_for_execution("absent") == []


class TestQueries:
    def test_recent_global(self):
        audit.append(_entry())
        assert len(audit.recent_global()) >= 1

    def test_limit(self):
        for i in range(5):
            audit.append(_entry(order=i))
        assert len(audit.entries_for_execution("exec-1", limit=2)) == 2

    def test_stats(self):
        audit.append(_entry())
        s = audit.stats()
        for k in ["total_entries", "execution_keys", "global_buffered"]:
            assert k in s
        assert s["total_entries"] == 1


class TestReset:
    def test_reset(self):
        audit.append(_entry())
        audit._reset_for_testing()
        assert audit.total() == 0
