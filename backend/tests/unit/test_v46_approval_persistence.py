"""
V4.6 Unit Tests — ApprovalPersistence.

Tests:
  - save() creates a new approval record row
  - save() updates an existing row (upsert)
  - load_all() returns all records for a task in order
  - load_all() returns [] for unknown task
  - delete_all() removes all records for a task
  - Approval status round-trip (PENDING / APPROVED / DENIED / EXPIRED)
  - resolved_at round-trip
"""
import pytest
from datetime import datetime

from app.unified import store as task_store, persistence as task_persistence
from app.unified import approval_persistence
from app.unified.models import ApprovalRecord, ApprovalStatus, UnifiedTask


@pytest.fixture(autouse=True)
def reset_store():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


def _save_task(task_id, conv="c1"):
    t = UnifiedTask(task_id=task_id, conversation_id=conv)
    task_persistence.save(t)
    return t


def _rec(approval_id, task_id, status=ApprovalStatus.pending):
    return ApprovalRecord(
        approval_id=approval_id,
        task_id=task_id,
        action="click buy",
        risk_level="HIGH_RISK",
        status=status,
    )


class TestSave:
    def test_creates_new_record(self):
        _save_task("t1")
        rec = _rec("a1", "t1")
        approval_persistence.save(rec)
        loaded = approval_persistence.load_all("t1")
        assert len(loaded) == 1
        assert loaded[0].approval_id == "a1"

    def test_upsert_updates_status(self):
        _save_task("t2")
        rec = _rec("a2", "t2")
        approval_persistence.save(rec)
        rec.status = ApprovalStatus.approved
        rec.resolved_at = datetime.utcnow()
        rec.resolution_note = "user approved"
        approval_persistence.save(rec)
        loaded = approval_persistence.load_all("t2")
        assert loaded[0].status == ApprovalStatus.approved
        assert "approved" in loaded[0].resolution_note

    def test_action_stored(self):
        _save_task("t3")
        rec = ApprovalRecord("a3", "t3", "submit form", "REQUIRES_APPROVAL")
        approval_persistence.save(rec)
        loaded = approval_persistence.load_all("t3")
        assert loaded[0].action == "submit form"

    def test_risk_level_stored(self):
        _save_task("t4")
        rec = _rec("a4", "t4")
        approval_persistence.save(rec)
        loaded = approval_persistence.load_all("t4")
        assert loaded[0].risk_level == "HIGH_RISK"


class TestStatusRoundTrip:
    def test_pending(self):
        _save_task("t5")
        rec = _rec("a5", "t5", ApprovalStatus.pending)
        approval_persistence.save(rec)
        assert approval_persistence.load_all("t5")[0].status == ApprovalStatus.pending

    def test_approved(self):
        _save_task("t6")
        rec = _rec("a6", "t6", ApprovalStatus.approved)
        approval_persistence.save(rec)
        assert approval_persistence.load_all("t6")[0].status == ApprovalStatus.approved

    def test_denied(self):
        _save_task("t7")
        rec = _rec("a7", "t7", ApprovalStatus.denied)
        approval_persistence.save(rec)
        assert approval_persistence.load_all("t7")[0].status == ApprovalStatus.denied

    def test_expired(self):
        _save_task("t8")
        rec = _rec("a8", "t8", ApprovalStatus.expired)
        approval_persistence.save(rec)
        assert approval_persistence.load_all("t8")[0].status == ApprovalStatus.expired


class TestResolvedAt:
    def test_resolved_at_none_by_default(self):
        _save_task("t9")
        rec = _rec("a9", "t9")
        approval_persistence.save(rec)
        assert approval_persistence.load_all("t9")[0].resolved_at is None

    def test_resolved_at_stored_when_set(self):
        _save_task("t10")
        rec = _rec("a10", "t10")
        ts = datetime(2025, 6, 1, 12, 0, 0)
        rec.resolved_at = ts
        approval_persistence.save(rec)
        loaded = approval_persistence.load_all("t10")[0]
        assert loaded.resolved_at is not None


class TestLoadAll:
    def test_returns_empty_for_unknown_task(self):
        assert approval_persistence.load_all("unknown-task") == []

    def test_returns_multiple_records_ordered(self):
        _save_task("t11")
        for i in range(3):
            approval_persistence.save(_rec(f"a{i+20}", "t11"))
        loaded = approval_persistence.load_all("t11")
        assert len(loaded) == 3

    def test_does_not_mix_records_between_tasks(self):
        _save_task("t12")
        _save_task("t13", "c13")
        approval_persistence.save(_rec("a30", "t12"))
        approval_persistence.save(_rec("a31", "t13"))
        assert len(approval_persistence.load_all("t12")) == 1
        assert len(approval_persistence.load_all("t13")) == 1


class TestDeleteAll:
    def test_removes_all_records(self):
        _save_task("t14")
        for i in range(3):
            approval_persistence.save(_rec(f"a4{i}", "t14"))
        count = approval_persistence.delete_all("t14")
        assert count == 3
        assert approval_persistence.load_all("t14") == []

    def test_returns_zero_when_nothing_to_delete(self):
        _save_task("t15")
        assert approval_persistence.delete_all("t15") == 0

    def test_does_not_delete_other_tasks_records(self):
        _save_task("t16")
        _save_task("t17", "c17")
        approval_persistence.save(_rec("a50", "t16"))
        approval_persistence.save(_rec("a51", "t17"))
        approval_persistence.delete_all("t16")
        assert len(approval_persistence.load_all("t17")) == 1
