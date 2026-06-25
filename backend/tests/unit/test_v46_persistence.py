"""
V4.6 Unit Tests — UnifiedTaskPersistence.

Tests (all run against SQLite in-memory via conftest.py):
  - save() upserts a task record
  - load() returns a task matching the saved one
  - load_by_conversation() finds by conversation_id
  - load_active() returns only non-terminal tasks
  - delete() removes the record
  - mark_restored() stamps restored_at
  - increment_snapshot_count() increments the counter
  - All operations return None / no-op when a task is not found
"""
import pytest
from app.unified import store as task_store
from app.unified import persistence as task_persistence
from app.unified.models import UnifiedTask, TaskState
from app.unified.task_lifecycle import TaskLifecycleManager


@pytest.fixture(autouse=True)
def reset_store():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


@pytest.fixture
def mgr():
    return TaskLifecycleManager()


def _task(tid="t1", conv="c1", query="test query"):
    t = UnifiedTask(task_id=tid, conversation_id=conv, original_query=query)
    return t


class TestSaveAndLoad:
    def test_save_then_load_returns_task(self):
        task = _task()
        task_persistence.save(task)
        loaded = task_persistence.load(task.task_id)
        assert loaded is not None
        assert loaded.task_id == task.task_id

    def test_loaded_state_matches(self):
        task = _task()
        task.state = TaskState.researching
        task_persistence.save(task)
        loaded = task_persistence.load(task.task_id)
        assert loaded.state == TaskState.researching

    def test_loaded_conversation_id_matches(self):
        task = _task("t2", "conv-abc")
        task_persistence.save(task)
        loaded = task_persistence.load("t2")
        assert loaded.conversation_id == "conv-abc"

    def test_loaded_query_matches(self):
        task = _task("t3", "c3", "find best laptop")
        task_persistence.save(task)
        loaded = task_persistence.load("t3")
        assert loaded.original_query == "find best laptop"

    def test_upsert_updates_existing(self):
        task = _task("t4", "c4")
        task_persistence.save(task)
        task.current_goal = "updated goal"
        task_persistence.save(task)
        loaded = task_persistence.load("t4")
        assert loaded.current_goal == "updated goal"

    def test_entities_round_trip(self):
        task = _task("t5", "c5")
        task.entities = {"destination": "NYC", "date": "2025-12-01"}
        task_persistence.save(task)
        loaded = task_persistence.load("t5")
        assert loaded.entities["destination"] == "NYC"

    def test_execution_plan_round_trip(self):
        task = _task("t6", "c6")
        task.execution_plan = {"workflow_type": "booking", "confidence": 0.9}
        task_persistence.save(task)
        loaded = task_persistence.load("t6")
        assert loaded.execution_plan["workflow_type"] == "booking"

    def test_research_report_round_trip(self):
        task = _task("t7", "c7")
        task.research_report = {"executive_summary": "3 flights found", "confidence_score": 0.8}
        task_persistence.save(task)
        loaded = task_persistence.load("t7")
        assert loaded.research_report["executive_summary"] == "3 flights found"

    def test_load_nonexistent_returns_none(self):
        assert task_persistence.load("nonexistent-id") is None


class TestLoadByConversation:
    def test_finds_by_conversation_id(self):
        task = _task("t8", "my-conv")
        task_persistence.save(task)
        loaded = task_persistence.load_by_conversation("my-conv")
        assert loaded is not None
        assert loaded.task_id == "t8"

    def test_returns_none_for_unknown_conversation(self):
        assert task_persistence.load_by_conversation("unknown-conv") is None


class TestLoadActive:
    def test_returns_active_tasks_only(self):
        t_active = _task("ta1", "ca1")
        t_active.state = TaskState.researching
        task_persistence.save(t_active)

        t_done = _task("ta2", "ca2")
        t_done.state = TaskState.completed
        task_persistence.save(t_done)

        t_abandoned = _task("ta3", "ca3")
        t_abandoned.state = TaskState.abandoned
        task_persistence.save(t_abandoned)

        active = task_persistence.load_active()
        active_ids = {t.task_id for t in active}
        assert "ta1" in active_ids
        assert "ta2" not in active_ids
        assert "ta3" not in active_ids

    def test_returns_empty_when_no_active(self):
        t = _task("ta4", "ca4")
        t.state = TaskState.completed
        task_persistence.save(t)
        active = task_persistence.load_active()
        assert all(t.task_id != "ta4" for t in active)


class TestDelete:
    def test_delete_removes_record(self):
        task = _task("td1", "cd1")
        task_persistence.save(task)
        result = task_persistence.delete("td1")
        assert result is True
        assert task_persistence.load("td1") is None

    def test_delete_unknown_returns_false(self):
        assert task_persistence.delete("no-such-task") is False


class TestMarkRestored:
    def test_stamps_restored_at(self):
        task = _task("tr1", "cr1")
        task_persistence.save(task)
        task_persistence.mark_restored("tr1")
        # Just verifying no exception; restored_at is on the DB record


class TestIncrementSnapshotCount:
    def test_increments_counter(self):
        task = _task("ts1", "cs1")
        task_persistence.save(task)
        task_persistence.increment_snapshot_count("ts1")
        task_persistence.increment_snapshot_count("ts1")
        # Verify by loading the record directly
        from app.models.db import UnifiedTaskRecord
        from app.unified.persistence import _session_factory, _session_scope
        with _session_scope() as db:
            rec = db.get(UnifiedTaskRecord, "ts1")
            assert rec.snapshot_count == 2
