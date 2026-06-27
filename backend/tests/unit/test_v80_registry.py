"""
V8.0 Unit Tests — ApprovalRegistry (26 tests).
"""
import time
import pytest

from app.approvals import registry as reg
from app.approvals.models import (
    ApprovalStatus, ApprovalSourceType, ApprovalRiskLevel, make_approval_request,
)


@pytest.fixture(autouse=True)
def reset():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


def _make(risk=ApprovalRiskLevel.medium, mission_id=None, task_id=None):
    return make_approval_request(
        ApprovalSourceType.manual, "src", "Title", "Desc", risk,
        mission_id=mission_id, task_id=task_id,
    )


class TestRegistryAdd:
    def test_add_and_get(self):
        r = _make()
        reg.add(r)
        assert reg.get(r.approval_id) is not None

    def test_get_unknown_returns_none(self):
        assert reg.get("nonexistent") is None

    def test_count_increments(self):
        reg.add(_make())
        assert reg.count() == 1
        reg.add(_make())
        assert reg.count() == 2

    def test_by_mission_index(self):
        r = _make(mission_id="m1")
        reg.add(r)
        items = reg.list_for_mission("m1")
        assert any(i.approval_id == r.approval_id for i in items)

    def test_by_task_index(self):
        r = _make(task_id="t1")
        reg.add(r)
        items = reg.list_for_task("t1")
        assert any(i.approval_id == r.approval_id for i in items)


class TestRegistryApprove:
    def test_approve_pending(self):
        r = _make()
        reg.add(r)
        result = reg.approve(r.approval_id)
        assert result is True

    def test_approve_sets_status(self):
        r = _make()
        reg.add(r)
        reg.approve(r.approval_id)
        updated = reg.get(r.approval_id)
        assert updated.status == ApprovalStatus.approved

    def test_approve_sets_resolved_at(self):
        r = _make()
        reg.add(r)
        reg.approve(r.approval_id)
        assert reg.get(r.approval_id).resolved_at is not None

    def test_approve_sets_resolved_by(self):
        r = _make()
        reg.add(r)
        reg.approve(r.approval_id, decision_source="tester")
        assert reg.get(r.approval_id).resolved_by == "tester"

    def test_approve_nonexistent_returns_false(self):
        assert reg.approve("nope") is False

    def test_double_approve_returns_false(self):
        r = _make()
        reg.add(r)
        reg.approve(r.approval_id)
        assert reg.approve(r.approval_id) is False


class TestRegistryReject:
    def test_reject_pending(self):
        r = _make()
        reg.add(r)
        assert reg.reject(r.approval_id) is True

    def test_reject_sets_status(self):
        r = _make()
        reg.add(r)
        reg.reject(r.approval_id, reason="not safe")
        updated = reg.get(r.approval_id)
        assert updated.status == ApprovalStatus.rejected
        assert updated.rejection_reason == "not safe"

    def test_reject_nonexistent_returns_false(self):
        assert reg.reject("nope") is False


class TestRegistryExpireCancel:
    def test_expire_pending(self):
        r = _make()
        reg.add(r)
        assert reg.expire(r.approval_id) is True
        assert reg.get(r.approval_id).status == ApprovalStatus.expired

    def test_cancel_pending(self):
        r = _make()
        reg.add(r)
        assert reg.cancel(r.approval_id) is True
        assert reg.get(r.approval_id).status == ApprovalStatus.cancelled

    def test_cancel_approved_returns_false(self):
        r = _make()
        reg.add(r)
        reg.approve(r.approval_id)
        assert reg.cancel(r.approval_id) is False


class TestRegistryViews:
    def test_list_pending_only_pending(self):
        r1 = _make()
        r2 = _make()
        reg.add(r1); reg.add(r2)
        reg.approve(r1.approval_id)
        pending = reg.list_pending()
        assert not any(p.approval_id == r1.approval_id for p in pending)
        assert any(p.approval_id == r2.approval_id for p in pending)

    def test_list_critical_high_and_critical_only(self):
        reg.add(_make(ApprovalRiskLevel.critical))
        reg.add(_make(ApprovalRiskLevel.high))
        reg.add(_make(ApprovalRiskLevel.low))
        crit = reg.list_critical()
        assert len(crit) == 2
        assert all(r.risk_level in (ApprovalRiskLevel.critical, ApprovalRiskLevel.high)
                   for r in crit)

    def test_list_all_sorted_by_risk(self):
        reg.add(_make(ApprovalRiskLevel.low))
        reg.add(_make(ApprovalRiskLevel.critical))
        items = reg.list_all()
        assert items[0].risk_level == ApprovalRiskLevel.critical

    def test_stats_structure(self):
        s = reg.stats()
        for k in ("cached_items", "total_added", "total_evicted", "pending_count"):
            assert k in s

    def test_auto_expire_past_expires_at(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D",
                                   ApprovalRiskLevel.low, ttl_seconds=0.001)
        reg.add(r)
        time.sleep(0.02)
        fetched = reg.get(r.approval_id)
        assert fetched is None or fetched.status == ApprovalStatus.expired
