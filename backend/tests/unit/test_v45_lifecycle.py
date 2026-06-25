"""
V4.5 Unit Tests — TaskLifecycleManager.

Tests cover:
  - create() builds task in CREATED state
  - get_or_create() returns existing task on second call
  - transition() succeeds for valid transitions
  - transition() raises for invalid transitions
  - mark_researching / mark_research_complete / mark_workflow_started / etc.
  - auto-promote to READY_FOR_WORKFLOW when opportunity_detected=True
  - state_history tracks each transition
"""
import pytest

from app.unified import store as task_store
from app.unified.models import TaskState
from app.unified.task_lifecycle import (
    TaskLifecycleManager, TaskLifecycleError,
)


def setup_function():
    task_store._reset_for_testing()


@pytest.fixture
def mgr():
    return TaskLifecycleManager()


class TestCreate:
    def test_task_in_created_state(self, mgr):
        task = mgr.create("conv-1", "book a flight")
        assert task.state == TaskState.created

    def test_task_stored(self, mgr):
        task = mgr.create("conv-2", "research flights")
        assert task_store.get(task.task_id) is not None

    def test_task_indexed_by_conversation(self, mgr):
        task = mgr.create("conv-3", "q")
        found = task_store.get_by_conversation("conv-3")
        assert found is not None and found.task_id == task.task_id

    def test_query_stored(self, mgr):
        task = mgr.create("conv-4", "buy laptop")
        assert task.original_query == "buy laptop"

    def test_initial_timeline_has_user_message(self, mgr):
        task = mgr.create("conv-5", "summarize page")
        from app.unified.models import TimelineEventType
        msgs = task.timeline.by_type(TimelineEventType.user_message)
        assert len(msgs) == 1


class TestGetOrCreate:
    def test_returns_existing_on_second_call(self, mgr):
        t1 = mgr.create("conv-dup", "query")
        t2 = mgr.get_or_create("conv-dup", "other query")
        assert t1.task_id == t2.task_id

    def test_creates_new_when_missing(self, mgr):
        task = mgr.get_or_create("brand-new-conv", "q")
        assert task is not None
        assert task.state == TaskState.created


class TestValidTransition:
    def test_created_to_researching(self, mgr):
        task = mgr.create("c1", "q")
        mgr.transition(task, TaskState.researching, {"topic": "flights"})
        assert task.state == TaskState.researching

    def test_state_history_appended(self, mgr):
        task = mgr.create("c2", "q")
        mgr.transition(task, TaskState.researching)
        assert len(task.state_history) == 2
        assert task.state_history[-1][0] == TaskState.researching

    def test_full_research_path(self, mgr):
        task = mgr.create("c3", "q")
        mgr.transition(task, TaskState.researching)
        mgr.transition(task, TaskState.research_complete)
        mgr.transition(task, TaskState.ready_for_workflow)
        mgr.transition(task, TaskState.workflow_running)
        mgr.transition(task, TaskState.completed)
        assert task.state == TaskState.completed


class TestInvalidTransition:
    def test_created_to_completed_raises(self, mgr):
        task = mgr.create("cx", "q")
        with pytest.raises(TaskLifecycleError):
            mgr.transition(task, TaskState.completed)

    def test_completed_to_researching_raises(self, mgr):
        task = mgr.create("cy", "q")
        mgr.transition(task, TaskState.researching)
        mgr.transition(task, TaskState.research_complete)
        mgr.transition(task, TaskState.ready_for_workflow)
        mgr.transition(task, TaskState.workflow_running)
        mgr.transition(task, TaskState.completed)
        with pytest.raises(TaskLifecycleError):
            mgr.transition(task, TaskState.researching)


class TestNamedHelpers:
    def test_mark_researching(self, mgr):
        task = mgr.create("h1", "q")
        mgr.mark_researching(task, "flights")
        assert task.state == TaskState.researching

    def test_mark_research_complete_sets_session_id(self, mgr):
        task = mgr.create("h2", "q")
        mgr.mark_researching(task, "t")
        mgr.mark_research_complete(task, "sess-123", "flights")
        assert task.research_session_id == "sess-123"

    def test_auto_promote_when_opportunity_detected(self, mgr):
        task = mgr.create("h3", "q")
        mgr.mark_researching(task, "t")
        mgr.mark_research_complete(task, "s1", "flights", opportunity_detected=True)
        assert task.state == TaskState.ready_for_workflow

    def test_no_auto_promote_when_no_opportunity(self, mgr):
        task = mgr.create("h4", "q")
        mgr.mark_researching(task, "t")
        mgr.mark_research_complete(task, "s1", "flights", opportunity_detected=False)
        assert task.state == TaskState.research_complete

    def test_mark_workflow_started(self, mgr):
        task = mgr.create("h5", "q")
        mgr.mark_researching(task, "t")
        mgr.mark_research_complete(task, "s1", "t", opportunity_detected=True)
        mgr.mark_workflow_started(task, "ws-456")
        assert task.state == TaskState.workflow_running
        assert task.workflow_session_id == "ws-456"

    def test_mark_completed(self, mgr):
        task = mgr.create("h6", "q")
        mgr.mark_researching(task, "t")
        mgr.mark_research_complete(task, "s", "t", opportunity_detected=True)
        mgr.mark_workflow_started(task, "ws1")
        mgr.mark_completed(task, "done")
        assert task.state == TaskState.completed

    def test_mark_failed(self, mgr):
        task = mgr.create("h7", "q")
        mgr.mark_researching(task, "t")
        mgr.mark_failed(task, "engine error")
        assert task.state == TaskState.failed

    def test_mark_abandoned_from_created(self, mgr):
        task = mgr.create("h8", "q")
        mgr.mark_abandoned(task)
        assert task.state == TaskState.abandoned
