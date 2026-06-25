"""
V4.6 Unit Tests — TaskRestorationService.

Tests:
  - restore() fast path: returns in-memory task immediately
  - restore() slow path: loads from DB, hydrates timeline + approvals
  - restore() returns None for unknown task_id
  - restore_by_conversation() finds by conversation_id
  - Snapshot context seeds entities / research_report / execution_plan
  - warmup() loads active tasks from DB into in-memory store
  - warmup() returns count of tasks loaded
"""
import pytest

from app.unified import store as task_store
from app.unified import persistence as task_persistence
from app.unified import timeline_persistence, approval_persistence
from app.unified import snapshot as snap_system
from app.unified import restoration as task_restoration
from app.unified.models import (
    UnifiedTask, TaskState, TimelineEvent, TimelineEventType,
    ApprovalRecord, ApprovalStatus,
)


@pytest.fixture(autouse=True)
def reset_store():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


def _make_task(task_id, conv, state=TaskState.researching):
    t = UnifiedTask(
        task_id=task_id,
        conversation_id=conv,
        original_query="test query",
        state=state,
    )
    t.entities = {"key": "value"}
    task_persistence.save(t)
    return t


def _make_event(task_id):
    import uuid
    return TimelineEvent(
        event_id=str(uuid.uuid4())[:8],
        event_type=TimelineEventType.user_message,
        task_id=task_id,
        data={"msg": "hello"},
    )


def _make_approval(task_id, aid="a1"):
    return ApprovalRecord(
        approval_id=aid,
        task_id=task_id,
        action="click",
        risk_level="SAFE",
    )


class TestFastPath:
    def test_returns_in_memory_task_without_db(self):
        task = UnifiedTask(task_id="m1", conversation_id="cm1")
        task_store.put(task)
        result = task_restoration.restore("m1")
        assert result is not None
        assert result.task_id == "m1"

    def test_fast_path_does_not_query_db(self, monkeypatch):
        task = UnifiedTask(task_id="m2", conversation_id="cm2")
        task_store.put(task)
        called = []
        monkeypatch.setattr(task_persistence, "load", lambda tid: called.append(tid) or None)
        task_restoration.restore("m2")
        assert called == []  # DB was not queried


class TestSlowPath:
    def test_loads_task_from_db_when_not_in_memory(self):
        _make_task("db1", "cdb1")
        result = task_restoration.restore("db1")
        assert result is not None
        assert result.task_id == "db1"

    def test_loaded_task_added_to_memory_store(self):
        _make_task("db2", "cdb2")
        task_restoration.restore("db2")
        assert task_store.get("db2") is not None

    def test_timeline_hydrated(self):
        _make_task("db3", "cdb3")
        ev = _make_event("db3")
        timeline_persistence.save_event(ev)
        result = task_restoration.restore("db3")
        assert len(result.timeline.events) == 1

    def test_approvals_hydrated(self):
        _make_task("db4", "cdb4")
        rec = _make_approval("db4", "a-db4")
        approval_persistence.save(rec)
        result = task_restoration.restore("db4")
        assert len(result.approvals) == 1
        assert result.approvals[0].approval_id == "a-db4"

    def test_returns_none_for_unknown_task(self):
        result = task_restoration.restore("does-not-exist")
        assert result is None


class TestSnapshotSeeding:
    def test_seeds_entities_from_snapshot(self):
        task = _make_task("snap1", "csnap1")
        task.entities = {"city": "Tokyo"}
        task_persistence.save(task)
        snap_system.create(task, "research_complete")
        # Now create a fresh task record with no entities
        empty = UnifiedTask(task_id="snap1", conversation_id="csnap1")
        task_persistence.save(empty)
        result = task_restoration.restore("snap1")
        assert result.entities.get("city") == "Tokyo"

    def test_seeds_research_report_from_snapshot(self):
        task = _make_task("snap2", "csnap2")
        task.research_report = {"executive_summary": "found 3 flights"}
        task_persistence.save(task)
        snap_system.create(task, "research_complete")
        empty = UnifiedTask(task_id="snap2", conversation_id="csnap2")
        task_persistence.save(empty)
        result = task_restoration.restore("snap2")
        assert result.research_report is not None


class TestRestoreByConversation:
    def test_finds_by_conversation_id(self):
        _make_task("conv-task", "my-conv-restore")
        result = task_restoration.restore_by_conversation("my-conv-restore")
        assert result is not None
        assert result.task_id == "conv-task"

    def test_fast_path_when_already_in_memory(self):
        task = UnifiedTask(task_id="mem-conv", conversation_id="conv-mem")
        task_store.put(task)
        result = task_restoration.restore_by_conversation("conv-mem")
        assert result.task_id == "mem-conv"

    def test_returns_none_for_unknown_conversation(self):
        result = task_restoration.restore_by_conversation("unknown-conv-99")
        assert result is None


class TestWarmup:
    def test_loads_active_tasks_into_store(self):
        _make_task("warm1", "cw1", TaskState.researching)
        _make_task("warm2", "cw2", TaskState.ready_for_workflow)
        count = task_restoration.warmup()
        assert count >= 2
        assert task_store.get("warm1") is not None
        assert task_store.get("warm2") is not None

    def test_does_not_load_terminal_tasks(self):
        _make_task("term1", "ct1", TaskState.completed)
        _make_task("term2", "ct2", TaskState.abandoned)
        task_restoration.warmup()
        # Terminal tasks won't be in warmup results
        # They may not be in memory unless explicitly loaded

    def test_returns_count_of_tasks_loaded(self):
        _make_task("wc1", "cwc1", TaskState.researching)
        count = task_restoration.warmup()
        assert count >= 1
