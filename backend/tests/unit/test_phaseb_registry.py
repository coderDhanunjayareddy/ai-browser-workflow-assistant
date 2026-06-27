"""Phase B Execution Gateway — Unit tests: registry.py."""
import time
import pytest
from app.execution_gateway import registry as reg
from app.execution_gateway.registry import ExecutionRegistry
from app.execution_gateway.models import ExecutionState, make_execution


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


def _rec(plan="plan-1", mission="m-1", created=None):
    return make_execution(plan, "auth-1", mission_id=mission, task_id="t-1",
                          total_steps=3, adapter_name="mock",
                          created_at=created if created is not None else time.time())


class TestAddGet:
    def test_add_get(self):
        r = _rec()
        reg.add(r)
        assert reg.get(r.execution_id) is not None

    def test_get_missing(self):
        assert reg.get("absent") is None

    def test_count(self):
        reg.add(_rec()); reg.add(_rec())
        assert reg.count() == 2

    def test_list_all(self):
        reg.add(_rec()); reg.add(_rec())
        assert len(reg.list_all()) == 2

    def test_list_all_sorted(self):
        reg.add(_rec(created=100.0)); reg.add(_rec(created=200.0))
        assert reg.list_all()[0].created_at >= reg.list_all()[1].created_at


class TestIndexes:
    def test_list_for_mission(self):
        reg.add(_rec(mission="m-A")); reg.add(_rec(mission="m-A")); reg.add(_rec(mission="m-B"))
        assert len(reg.list_for_mission("m-A")) == 2

    def test_list_for_plan(self):
        reg.add(_rec(plan="p-A")); reg.add(_rec(plan="p-B"))
        assert len(reg.list_for_plan("p-A")) == 1

    def test_summary_for_mission(self):
        reg.add(_rec(mission="m-S"))
        s = reg.summary_for_mission("m-S")
        for k in ["total_executions", "running_executions", "completed_executions",
                  "failed_executions", "aborted_executions", "latest_execution_id",
                  "latest_state", "execution_ids"]:
            assert k in s
        assert s["total_executions"] == 1

    def test_summary_counts_by_state(self):
        r1 = _rec(mission="m-X"); r1.state = ExecutionState.completed
        r2 = _rec(mission="m-X"); r2.state = ExecutionState.failed
        reg.add(r1); reg.add(r2)
        s = reg.summary_for_mission("m-X")
        assert s["completed_executions"] == 1
        assert s["failed_executions"] == 1

    def test_summary_empty(self):
        assert reg.summary_for_mission("absent")["total_executions"] == 0


class TestStateCounts:
    def test_count_by_state(self):
        r = _rec(); r.state = ExecutionState.completed
        reg.add(r)
        assert reg.count_by_state(ExecutionState.completed) == 1
        assert reg.count_by_state(ExecutionState.running) == 0


class TestTTL:
    def test_expires(self):
        r = ExecutionRegistry(ttl=0.05)
        rec = _rec()
        r.add(rec)
        time.sleep(0.08)
        assert r.get(rec.execution_id) is None

    def test_expired_not_counted(self):
        r = ExecutionRegistry(ttl=0.05)
        r.add(_rec())
        time.sleep(0.08)
        assert r.count() == 0


class TestStats:
    def test_stats_keys(self):
        for k in ["cached_executions", "total_added", "total_evicted", "running_count",
                  "mission_keys", "plan_keys"]:
            assert k in reg.stats()

    def test_total_added(self):
        reg.add(_rec()); reg.add(_rec())
        assert reg.stats()["total_added"] == 2

    def test_reset(self):
        reg.add(_rec())
        reg._reset_for_testing()
        assert reg.count() == 0
