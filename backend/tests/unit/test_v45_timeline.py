"""
V4.5 Unit Tests — TaskTimelineManager.

Tests cover:
  - append() returns TimelineEvent with correct fields
  - typed helpers (record_user_message, record_research_started, etc.)
  - get_ordered() sorts by timestamp
  - get_summary() returns serializable dicts
  - event_id uniqueness
"""
import pytest
from datetime import datetime, timedelta

from app.unified import store as task_store
from app.unified.models import UnifiedTask, TimelineEventType
from app.unified.task_timeline import TaskTimelineManager


def setup_function():
    task_store._reset_for_testing()


def _task():
    t = UnifiedTask(task_id="t1", conversation_id="c1")
    task_store.put(t)
    return t


@pytest.fixture
def mgr():
    return TaskTimelineManager()


class TestAppend:
    def test_returns_timeline_event(self, mgr):
        task = _task()
        ev = mgr.append(task, TimelineEventType.user_message, {"msg": "hello"})
        assert ev.event_type == TimelineEventType.user_message

    def test_event_id_is_string(self, mgr):
        task = _task()
        ev = mgr.append(task, TimelineEventType.failure, {})
        assert isinstance(ev.event_id, str) and len(ev.event_id) > 0

    def test_event_attached_to_task(self, mgr):
        task = _task()
        mgr.append(task, TimelineEventType.user_message, {})
        assert len(task.timeline.events) == 1

    def test_custom_timestamp(self, mgr):
        task = _task()
        ts = datetime(2025, 1, 1, 12, 0, 0)
        ev = mgr.append(task, TimelineEventType.research_started, {}, timestamp=ts)
        assert ev.timestamp == ts


class TestTypedHelpers:
    def test_record_user_message(self, mgr):
        task = _task()
        ev = mgr.record_user_message(task, "book a flight")
        assert ev.event_type == TimelineEventType.user_message
        assert ev.data["message"] == "book a flight"

    def test_record_assistant_response_truncates(self, mgr):
        task = _task()
        long_response = "A" * 500
        ev = mgr.record_assistant_response(task, "answer", long_response)
        assert len(ev.data["summary"]) <= 200

    def test_record_research_started(self, mgr):
        task = _task()
        ev = mgr.record_research_started(task, "flights")
        assert ev.event_type == TimelineEventType.research_started
        assert ev.data["topic"] == "flights"

    def test_record_research_completed(self, mgr):
        task = _task()
        ev = mgr.record_research_completed(task, "flights", 0.8, 3)
        assert ev.data["confidence"] == 0.8
        assert ev.data["source_count"] == 3

    def test_record_workflow_prepared(self, mgr):
        task = _task()
        ev = mgr.record_workflow_prepared(task, "booking_workflow", "REQUIRES_APPROVAL")
        assert ev.event_type == TimelineEventType.workflow_prepared

    def test_record_workflow_started(self, mgr):
        task = _task()
        ev = mgr.record_workflow_started(task, "sess-1")
        assert ev.data["session_id"] == "sess-1"

    def test_record_workflow_completed(self, mgr):
        task = _task()
        ev = mgr.record_workflow_completed(task, 5, True)
        assert ev.data["steps_completed"] == 5
        assert ev.data["success"] is True

    def test_record_approval_requested(self, mgr):
        task = _task()
        ev = mgr.record_approval_requested(task, "click buy", "HIGH_RISK")
        assert ev.event_type == TimelineEventType.approval_requested

    def test_record_approval_granted(self, mgr):
        task = _task()
        ev = mgr.record_approval_granted(task, "submit form")
        assert ev.event_type == TimelineEventType.approval_granted

    def test_record_approval_denied(self, mgr):
        task = _task()
        ev = mgr.record_approval_denied(task, "transfer money", "too risky")
        assert ev.event_type == TimelineEventType.approval_denied
        assert ev.data["reason"] == "too risky"

    def test_record_failure(self, mgr):
        task = _task()
        ev = mgr.record_failure(task, "AI timeout", "research")
        assert ev.event_type == TimelineEventType.failure


class TestGetOrdered:
    def test_returns_sorted_by_timestamp(self, mgr):
        task = _task()
        now = datetime.utcnow()
        mgr.append(task, TimelineEventType.user_message, {}, timestamp=now + timedelta(seconds=2))
        mgr.append(task, TimelineEventType.research_started, {}, timestamp=now)
        ordered = mgr.get_ordered(task)
        assert ordered[0].event_type == TimelineEventType.research_started
        assert ordered[1].event_type == TimelineEventType.user_message


class TestGetSummary:
    def test_returns_list_of_dicts(self, mgr):
        task = _task()
        mgr.record_user_message(task, "q")
        summary = mgr.get_summary(task)
        assert isinstance(summary, list)
        assert "event_id" in summary[0]
        assert "type" in summary[0]
        assert "timestamp" in summary[0]
        assert "data" in summary[0]

    def test_type_is_string(self, mgr):
        task = _task()
        mgr.record_user_message(task, "q")
        s = mgr.get_summary(task)
        assert isinstance(s[0]["type"], str)


class TestEventIdUniqueness:
    def test_all_event_ids_unique(self, mgr):
        task = _task()
        for _ in range(20):
            mgr.record_user_message(task, "q")
        ids = [e.event_id for e in task.timeline.events]
        assert len(ids) == len(set(ids))
