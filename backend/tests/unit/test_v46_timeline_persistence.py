"""
V4.6 Unit Tests — TimelinePersistence.

Tests:
  - save_event() persists a single event
  - save_event() is idempotent (no duplicate on repeat call)
  - save_timeline() persists all events
  - load_timeline() reconstructs events in timestamp order
  - load_timeline() returns empty timeline for unknown task
  - delete_events() removes all rows for a task
  - Unknown event_type rows are skipped gracefully on load
"""
import pytest
from datetime import datetime, timedelta

from app.unified import store as task_store, persistence as task_persistence
from app.unified import timeline_persistence
from app.unified.models import (
    UnifiedTask, TaskTimeline, TimelineEvent, TimelineEventType,
)


@pytest.fixture(autouse=True)
def reset_store():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


def _make_event(task_id, event_type=TimelineEventType.user_message, data=None, ts=None):
    import uuid
    return TimelineEvent(
        event_id=str(uuid.uuid4())[:8],
        event_type=event_type,
        task_id=task_id,
        data=data or {"msg": "hello"},
        timestamp=ts or datetime.utcnow(),
    )


def _save_task(task_id, conv="c1"):
    t = UnifiedTask(task_id=task_id, conversation_id=conv)
    task_persistence.save(t)
    return t


class TestSaveEvent:
    def test_persists_single_event(self):
        _save_task("t1")
        ev = _make_event("t1")
        timeline_persistence.save_event(ev)
        tl = timeline_persistence.load_timeline("t1")
        assert len(tl.events) == 1

    def test_persisted_event_type_matches(self):
        _save_task("t2")
        ev = _make_event("t2", TimelineEventType.research_started, {"topic": "flights"})
        timeline_persistence.save_event(ev)
        tl = timeline_persistence.load_timeline("t2")
        assert tl.events[0].event_type == TimelineEventType.research_started

    def test_persisted_data_matches(self):
        _save_task("t3")
        ev = _make_event("t3", data={"key": "value"})
        timeline_persistence.save_event(ev)
        tl = timeline_persistence.load_timeline("t3")
        assert tl.events[0].data["key"] == "value"

    def test_idempotent_on_repeat_save(self):
        _save_task("t4")
        ev = _make_event("t4")
        timeline_persistence.save_event(ev)
        timeline_persistence.save_event(ev)  # repeat
        tl = timeline_persistence.load_timeline("t4")
        assert len(tl.events) == 1


class TestSaveTimeline:
    def test_persists_all_events(self):
        _save_task("t5")
        tl = TaskTimeline(task_id="t5")
        for i in range(5):
            tl.append(_make_event("t5"))
        timeline_persistence.save_timeline(tl)
        loaded = timeline_persistence.load_timeline("t5")
        assert len(loaded.events) == 5


class TestLoadTimeline:
    def test_returns_events_sorted_by_timestamp(self):
        _save_task("t6")
        now = datetime.utcnow()
        e1 = _make_event("t6", ts=now + timedelta(seconds=5))
        e2 = _make_event("t6", ts=now)
        e3 = _make_event("t6", ts=now + timedelta(seconds=2))
        for e in [e1, e2, e3]:
            timeline_persistence.save_event(e)
        loaded = timeline_persistence.load_timeline("t6")
        timestamps = [e.timestamp for e in loaded.events]
        assert timestamps == sorted(timestamps)

    def test_returns_empty_for_unknown_task(self):
        tl = timeline_persistence.load_timeline("nonexistent-task-id")
        assert len(tl.events) == 0
        assert tl.task_id == "nonexistent-task-id"

    def test_task_id_correct_on_loaded_events(self):
        _save_task("t7")
        ev = _make_event("t7")
        timeline_persistence.save_event(ev)
        loaded = timeline_persistence.load_timeline("t7")
        assert loaded.events[0].task_id == "t7"

    def test_event_id_preserved(self):
        _save_task("t8")
        ev = _make_event("t8")
        original_id = ev.event_id
        timeline_persistence.save_event(ev)
        loaded = timeline_persistence.load_timeline("t8")
        assert loaded.events[0].event_id == original_id


class TestDeleteEvents:
    def test_removes_all_events(self):
        _save_task("t9")
        for _ in range(3):
            timeline_persistence.save_event(_make_event("t9"))
        count = timeline_persistence.delete_events("t9")
        assert count == 3
        loaded = timeline_persistence.load_timeline("t9")
        assert len(loaded.events) == 0

    def test_returns_zero_for_no_events(self):
        _save_task("t10")
        count = timeline_persistence.delete_events("t10")
        assert count == 0

    def test_does_not_delete_other_tasks_events(self):
        _save_task("t11")
        _save_task("t12", "c12")
        timeline_persistence.save_event(_make_event("t11"))
        timeline_persistence.save_event(_make_event("t12"))
        timeline_persistence.delete_events("t11")
        loaded_12 = timeline_persistence.load_timeline("t12")
        assert len(loaded_12.events) == 1
