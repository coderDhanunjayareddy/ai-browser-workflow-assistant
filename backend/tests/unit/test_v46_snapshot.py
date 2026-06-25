"""
V4.6 Unit Tests — TaskSnapshotSystem.

Tests:
  - create() saves snapshot at valid trigger
  - create() returns None for unknown trigger
  - create() returns snapshot_id string
  - load_latest() returns most recent snapshot
  - load_latest() returns None when no snapshots exist
  - load_all() returns list newest-first
  - count() returns correct count
  - Snapshot context captures entities, research_report, execution_plan
  - snapshot_count incremented on parent task record
"""
import pytest

from app.unified import store as task_store, persistence as task_persistence
from app.unified import snapshot as snap_system
from app.unified.models import UnifiedTask, TaskState


@pytest.fixture(autouse=True)
def reset_store():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


def _save_task(task_id, conv="c1"):
    t = UnifiedTask(task_id=task_id, conversation_id=conv)
    task_persistence.save(t)
    return t


def _rich_task(task_id):
    t = UnifiedTask(
        task_id=task_id,
        conversation_id=f"conv-{task_id}",
        original_query="book a flight to NYC",
        current_goal="book cheapest flight to NYC",
        state=TaskState.research_complete,
    )
    t.entities = {"destination": "NYC", "date": "2025-12-01"}
    t.research_report = {"executive_summary": "5 flights found", "confidence_score": 0.85}
    t.execution_plan = {"workflow_type": "booking", "confidence": 0.9}
    task_persistence.save(t)
    return t


class TestCreate:
    def test_returns_snapshot_id_string(self):
        task = _save_task("t1")
        sid = snap_system.create(task, "research_complete")
        assert isinstance(sid, str) and len(sid) > 0

    def test_returns_none_for_invalid_trigger(self):
        task = _save_task("t2")
        sid = snap_system.create(task, "not_a_real_trigger")
        assert sid is None

    def test_valid_triggers_all_work(self):
        for i, trigger in enumerate(snap_system.SNAPSHOT_TRIGGERS):
            task = _save_task(f"trigger-{i}", f"c{i}")
            sid = snap_system.create(task, trigger)
            assert sid is not None, f"Failed for trigger: {trigger}"

    def test_captures_entities(self):
        task = _rich_task("t3")
        snap_system.create(task, "research_complete")
        snap = snap_system.load_latest("t3")
        assert snap["entities"]["destination"] == "NYC"

    def test_captures_research_report(self):
        task = _rich_task("t4")
        snap_system.create(task, "research_complete")
        snap = snap_system.load_latest("t4")
        assert snap["research_report"]["executive_summary"] == "5 flights found"

    def test_captures_execution_plan(self):
        task = _rich_task("t5")
        snap_system.create(task, "workflow_prepared")
        snap = snap_system.load_latest("t5")
        assert snap["execution_plan"]["workflow_type"] == "booking"

    def test_captures_task_state(self):
        task = _rich_task("t6")
        snap_system.create(task, "research_complete")
        snap = snap_system.load_latest("t6")
        assert snap["task_state"] == "RESEARCH_COMPLETE"

    def test_captures_timeline_length(self):
        task = _rich_task("t7")
        snap_system.create(task, "research_complete")
        snap = snap_system.load_latest("t7")
        assert "timeline_length" in snap


class TestLoadLatest:
    def test_returns_none_when_no_snapshots(self):
        _save_task("t8")
        assert snap_system.load_latest("t8") is None

    def test_returns_most_recent(self):
        task = _save_task("t9")
        snap_system.create(task, "research_complete")
        snap_system.create(task, "workflow_prepared")
        snap = snap_system.load_latest("t9")
        assert snap["trigger"] == "workflow_prepared"

    def test_has_snapshot_id(self):
        task = _save_task("t10")
        snap_system.create(task, "research_complete")
        snap = snap_system.load_latest("t10")
        assert "snapshot_id" in snap

    def test_has_created_at(self):
        task = _save_task("t11")
        snap_system.create(task, "workflow_started")
        snap = snap_system.load_latest("t11")
        assert "created_at" in snap


class TestLoadAll:
    def test_returns_newest_first(self):
        task = _save_task("t12")
        snap_system.create(task, "research_complete")
        snap_system.create(task, "workflow_prepared")
        snaps = snap_system.load_all("t12")
        assert len(snaps) == 2
        assert snaps[0]["trigger"] == "workflow_prepared"

    def test_returns_empty_for_unknown_task(self):
        assert snap_system.load_all("unknown-task") == []


class TestCount:
    def test_returns_correct_count(self):
        task = _save_task("t13")
        snap_system.create(task, "research_complete")
        snap_system.create(task, "workflow_prepared")
        assert snap_system.count("t13") == 2

    def test_returns_zero_for_no_snapshots(self):
        _save_task("t14")
        assert snap_system.count("t14") == 0


class TestSnapshotCountOnParent:
    def test_parent_record_snapshot_count_incremented(self):
        task = _save_task("t15")
        snap_system.create(task, "research_complete")
        snap_system.create(task, "workflow_prepared")
        from app.models.db import UnifiedTaskRecord
        from app.unified.persistence import _session_scope
        with _session_scope() as db:
            rec = db.get(UnifiedTaskRecord, "t15")
            assert rec.snapshot_count == 2
