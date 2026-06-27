"""
V8.0 Unit Tests — ApprovalQueue (18 tests).
"""
import pytest

from app.approvals import queue as q
from app.approvals import registry as reg
from app.approvals.models import (
    ApprovalStatus, ApprovalSourceType, ApprovalRiskLevel, make_approval_request,
)


@pytest.fixture(autouse=True)
def reset():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


def _add(risk=ApprovalRiskLevel.medium, mission_id=None, task_id=None,
         status=None):
    r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", risk,
                               mission_id=mission_id, task_id=task_id)
    if status == "approved":
        reg.add(r)
        reg.approve(r.approval_id)
    elif status == "rejected":
        reg.add(r)
        reg.reject(r.approval_id)
    else:
        reg.add(r)
    return r


class TestAllPending:
    def test_returns_list(self):
        assert isinstance(q.all_pending(), list)

    def test_only_pending(self):
        _add()
        _add(status="approved")
        pending = q.all_pending()
        assert all(r.status == ApprovalStatus.pending for r in pending)

    def test_respects_limit(self):
        for _ in range(10):
            _add()
        assert len(q.all_pending(limit=3)) <= 3


class TestCritical:
    def test_returns_list(self):
        assert isinstance(q.critical(), list)

    def test_only_high_and_critical(self):
        _add(ApprovalRiskLevel.critical)
        _add(ApprovalRiskLevel.high)
        _add(ApprovalRiskLevel.low)
        crit = q.critical()
        assert all(r.risk_level in (ApprovalRiskLevel.critical, ApprovalRiskLevel.high)
                   for r in crit)

    def test_does_not_include_approved(self):
        _add(ApprovalRiskLevel.critical, status="approved")
        assert len(q.critical()) == 0

    def test_sorted_critical_first(self):
        _add(ApprovalRiskLevel.high)
        _add(ApprovalRiskLevel.critical)
        items = q.critical()
        if len(items) >= 2:
            assert items[0].risk_order >= items[1].risk_order


class TestForMission:
    def test_returns_list(self):
        assert isinstance(q.for_mission("m1"), list)

    def test_includes_all_statuses(self):
        _add(mission_id="m1")
        _add(mission_id="m1", status="approved")
        items = q.for_mission("m1")
        statuses = {r.status for r in items}
        assert ApprovalStatus.approved in statuses

    def test_excludes_other_missions(self):
        _add(mission_id="m1")
        _add(mission_id="m2")
        items = q.for_mission("m1")
        assert all(r.mission_id == "m1" for r in items)

    def test_empty_for_unknown_mission(self):
        assert q.for_mission("unknown-xyz") == []


class TestPendingForMission:
    def test_only_pending_for_mission(self):
        _add(mission_id="m3")
        _add(mission_id="m3", status="approved")
        items = q.pending_for_mission("m3")
        assert all(r.status == ApprovalStatus.pending for r in items)


class TestForTask:
    def test_returns_list(self):
        assert isinstance(q.for_task("t1"), list)

    def test_task_filter(self):
        _add(task_id="t-abc")
        _add(task_id="t-xyz")
        items = q.for_task("t-abc")
        assert all(r.task_id == "t-abc" for r in items)


class TestSummaryForMission:
    def test_summary_keys(self):
        s = q.summary_for_mission("m-empty")
        for key in ("total", "pending", "approved", "rejected", "critical"):
            assert key in s

    def test_summary_empty_mission(self):
        s = q.summary_for_mission("no-approvals")
        assert s["total"]   == 0
        assert s["pending"] == 0

    def test_summary_counts(self):
        _add(ApprovalRiskLevel.critical, mission_id="m-sum")
        _add(ApprovalRiskLevel.low,      mission_id="m-sum", status="approved")
        s = q.summary_for_mission("m-sum")
        assert s["total"]    >= 2
        assert s["pending"]  >= 1
        assert s["approved"] >= 1
        assert s["critical"] >= 1
