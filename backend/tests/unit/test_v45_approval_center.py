"""
V4.5 Unit Tests — ApprovalCenter.

Tests cover:
  - request() creates PENDING record
  - approve() marks APPROVED and sets resolved_at
  - deny() marks DENIED
  - approve() returns None on unknown approval_id
  - expire_pending() expires all pending records
  - pending() query
  - history() returns all records
  - timeline events appended during lifecycle
"""
import pytest

from app.unified import store as task_store
from app.unified.models import UnifiedTask, ApprovalStatus, TimelineEventType
from app.unified.approval_center import ApprovalCenter


def setup_function():
    task_store._reset_for_testing()


def _task():
    t = UnifiedTask(task_id="t1", conversation_id="c1")
    task_store.put(t)
    return t


@pytest.fixture
def ac():
    return ApprovalCenter()


class TestRequest:
    def test_creates_pending_record(self, ac):
        task = _task()
        rec = ac.request(task, "click buy", "HIGH_RISK")
        assert rec.status == ApprovalStatus.pending

    def test_record_attached_to_task(self, ac):
        task = _task()
        ac.request(task, "submit form", "REQUIRES_APPROVAL")
        assert len(task.approvals) == 1

    def test_approval_id_is_string(self, ac):
        task = _task()
        rec = ac.request(task, "click", "SAFE")
        assert isinstance(rec.approval_id, str) and len(rec.approval_id) > 0

    def test_timeline_event_appended(self, ac):
        task = _task()
        ac.request(task, "buy now", "HIGH_RISK")
        events = task.timeline.by_type(TimelineEventType.approval_requested)
        assert len(events) == 1

    def test_action_stored(self, ac):
        task = _task()
        rec = ac.request(task, "fill password field", "REQUIRES_APPROVAL")
        assert rec.action == "fill password field"

    def test_risk_level_stored(self, ac):
        task = _task()
        rec = ac.request(task, "submit", "HIGH_RISK")
        assert rec.risk_level == "HIGH_RISK"


class TestApprove:
    def test_status_becomes_approved(self, ac):
        task = _task()
        rec = ac.request(task, "click", "SAFE")
        result = ac.approve(task, rec.approval_id, note="looks fine")
        assert result.status == ApprovalStatus.approved

    def test_resolved_at_set(self, ac):
        task = _task()
        rec = ac.request(task, "click", "SAFE")
        result = ac.approve(task, rec.approval_id)
        assert result.resolved_at is not None

    def test_note_stored(self, ac):
        task = _task()
        rec = ac.request(task, "click", "SAFE")
        result = ac.approve(task, rec.approval_id, note="user confirmed")
        assert "confirmed" in result.resolution_note

    def test_timeline_event_appended(self, ac):
        task = _task()
        rec = ac.request(task, "click", "SAFE")
        ac.approve(task, rec.approval_id)
        events = task.timeline.by_type(TimelineEventType.approval_granted)
        assert len(events) == 1

    def test_returns_none_for_unknown_id(self, ac):
        task = _task()
        result = ac.approve(task, "nonexistent-id")
        assert result is None

    def test_cannot_approve_already_resolved(self, ac):
        task = _task()
        rec = ac.request(task, "click", "SAFE")
        ac.approve(task, rec.approval_id)
        result = ac.approve(task, rec.approval_id)
        assert result is None


class TestDeny:
    def test_status_becomes_denied(self, ac):
        task = _task()
        rec = ac.request(task, "transfer money", "HIGH_RISK")
        result = ac.deny(task, rec.approval_id, reason="user denied")
        assert result.status == ApprovalStatus.denied

    def test_timeline_event_appended(self, ac):
        task = _task()
        rec = ac.request(task, "delete account", "HIGH_RISK")
        ac.deny(task, rec.approval_id)
        events = task.timeline.by_type(TimelineEventType.approval_denied)
        assert len(events) == 1

    def test_returns_none_for_unknown_id(self, ac):
        task = _task()
        result = ac.deny(task, "nope")
        assert result is None


class TestExpirePending:
    def test_pending_become_expired(self, ac):
        task = _task()
        ac.request(task, "a1", "SAFE")
        ac.request(task, "a2", "HIGH_RISK")
        count = ac.expire_pending(task)
        assert count == 2
        assert all(a.status == ApprovalStatus.expired for a in task.approvals)

    def test_already_resolved_not_expired(self, ac):
        task = _task()
        rec = ac.request(task, "a1", "SAFE")
        ac.approve(task, rec.approval_id)
        ac.request(task, "a2", "HIGH_RISK")
        count = ac.expire_pending(task)
        assert count == 1

    def test_returns_zero_when_nothing_pending(self, ac):
        task = _task()
        count = ac.expire_pending(task)
        assert count == 0


class TestQueries:
    def test_pending_filter(self, ac):
        task = _task()
        r1 = ac.request(task, "a", "SAFE")
        r2 = ac.request(task, "b", "HIGH_RISK")
        ac.approve(task, r1.approval_id)
        pending = ac.pending(task)
        assert len(pending) == 1
        assert pending[0].approval_id == r2.approval_id

    def test_history_returns_all(self, ac):
        task = _task()
        ac.request(task, "a", "SAFE")
        ac.request(task, "b", "HIGH_RISK")
        assert len(ac.history(task)) == 2
