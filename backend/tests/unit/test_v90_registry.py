"""V9.0 Execution Planning Layer — Unit tests: registry.py."""
import time
import pytest
from app.execution_planning import registry as reg
from app.execution_planning.registry import PlanRegistry
from app.execution_planning.models import (
    ActionType, TargetType, ExecutionMode, PlanStatus, make_step, make_plan,
)


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


def _plan(auth="auth-1", mission="m-1", task="t-1", created=None):
    return make_plan(auth, mission_id=mission, task_id=task,
                     created_at=created if created is not None else time.time(),
                     execution_mode=ExecutionMode.sequential,
                     steps=[make_step(1, ActionType.read, TargetType.page, "p")],
                     estimated_duration_ms=300, rollback_supported=True, confidence=0.6)


class TestAddGet:
    def test_add_then_get(self):
        p = _plan()
        reg.add(p)
        assert reg.get(p.plan_id) is not None

    def test_get_missing(self):
        assert reg.get("absent") is None

    def test_count(self):
        reg.add(_plan()); reg.add(_plan())
        assert reg.count() == 2

    def test_get_for_authorization_latest(self):
        p1 = _plan(auth="auth-X")
        reg.add(p1)
        p2 = _plan(auth="auth-X")
        reg.add(p2)
        assert reg.get_for_authorization("auth-X").plan_id == p2.plan_id

    def test_history_for_authorization(self):
        reg.add(_plan(auth="auth-H"))
        reg.add(_plan(auth="auth-H"))
        assert len(reg.history_for_authorization("auth-H")) == 2


class TestIndexes:
    def test_list_for_mission(self):
        reg.add(_plan(mission="m-A")); reg.add(_plan(mission="m-A")); reg.add(_plan(mission="m-B"))
        assert len(reg.list_for_mission("m-A")) == 2

    def test_list_for_task(self):
        reg.add(_plan(task="t-A")); reg.add(_plan(task="t-B"))
        assert len(reg.list_for_task("t-A")) == 1

    def test_list_all(self):
        reg.add(_plan()); reg.add(_plan())
        assert len(reg.list_all()) == 2

    def test_list_all_sorted_newest(self):
        reg.add(_plan(created=100.0))
        reg.add(_plan(created=200.0))
        plans = reg.list_all()
        assert plans[0].created_at >= plans[1].created_at

    def test_summary_for_mission(self):
        reg.add(_plan(mission="m-S"))
        s = reg.summary_for_mission("m-S")
        assert s["total_plans"] == 1
        for k in ["total_plans", "ready_plans", "draft_plans", "archived_plans", "active_plan_id", "plan_ids"]:
            assert k in s

    def test_summary_empty(self):
        assert reg.summary_for_mission("absent")["total_plans"] == 0


class TestStatusTransitions:
    def test_set_status(self):
        p = _plan()
        reg.add(p)
        assert reg.set_status(p.plan_id, PlanStatus.ready) is True
        assert reg.get(p.plan_id).status == PlanStatus.ready

    def test_set_status_missing(self):
        assert reg.set_status("absent", PlanStatus.ready) is False

    def test_mark_validated(self):
        p = _plan()
        reg.add(p)
        assert reg.mark_validated(p.plan_id, 123.0) is True
        assert reg.get(p.plan_id).validated_at == 123.0

    def test_archive(self):
        p = _plan()
        reg.add(p)
        assert reg.archive(p.plan_id, 123.0) is True
        assert reg.get(p.plan_id).status == PlanStatus.aborted
        assert reg.get(p.plan_id).archived_at == 123.0

    def test_archive_twice_false(self):
        p = _plan()
        reg.add(p)
        reg.archive(p.plan_id, 1.0)
        assert reg.archive(p.plan_id, 2.0) is False

    def test_archive_missing_false(self):
        assert reg.archive("absent", 1.0) is False

    def test_supersede(self):
        p1 = _plan(auth="auth-S")
        reg.add(p1)
        p2 = _plan(auth="auth-S")
        reg.add(p2)
        assert reg.supersede(p1.plan_id, p2.plan_id) is True
        assert reg.get(p1.plan_id).superseded_by == p2.plan_id
        assert reg.get(p1.plan_id).status == PlanStatus.aborted

    def test_count_by_status(self):
        p = _plan()
        reg.add(p)
        reg.set_status(p.plan_id, PlanStatus.ready)
        assert reg.count_by_status(PlanStatus.ready) == 1
        assert reg.count_by_status(PlanStatus.draft) == 0


class TestTTL:
    def test_plan_expires(self):
        r = PlanRegistry(ttl=0.05)
        p = _plan()
        r.add(p)
        time.sleep(0.08)
        assert r.get(p.plan_id) is None

    def test_expired_not_counted(self):
        r = PlanRegistry(ttl=0.05)
        r.add(_plan())
        time.sleep(0.08)
        assert r.count() == 0


class TestStats:
    def test_stats_keys(self):
        for k in ["cached_plans", "total_added", "total_evicted", "ready_count", "mission_keys", "task_keys"]:
            assert k in reg.stats()

    def test_total_added(self):
        reg.add(_plan()); reg.add(_plan())
        assert reg.stats()["total_added"] == 2

    def test_reset(self):
        reg.add(_plan())
        reg._reset_for_testing()
        assert reg.count() == 0
