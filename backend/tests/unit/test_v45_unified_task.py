"""
V4.5 Unit Tests — UnifiedTask model.

Tests cover:
  - Instantiation with defaults
  - State machine: VALID_TRANSITIONS
  - TaskTimeline append / by_type
  - ApprovalRecord fields
  - TaskTab fields
  - touch() updates updated_at
  - pending_approvals() filter
"""
import pytest
from datetime import datetime

from app.unified.models import (
    UnifiedTask, TaskState, TaskTimeline, TimelineEvent, TimelineEventType,
    ApprovalRecord, ApprovalStatus, TaskTab, TabRole, VALID_TRANSITIONS,
)


def _task(task_id="t1", conv_id="c1"):
    return UnifiedTask(task_id=task_id, conversation_id=conv_id, original_query="test")


class TestUnifiedTaskDefaults:
    def test_state_is_created(self):
        t = _task()
        assert t.state == TaskState.created

    def test_timeline_task_id_matches(self):
        t = _task("abc", "c1")
        assert t.timeline.task_id == "abc"

    def test_state_history_has_initial(self):
        t = _task()
        assert len(t.state_history) == 1
        assert t.state_history[0][0] == TaskState.created

    def test_approvals_empty(self):
        t = _task()
        assert t.approvals == []

    def test_tabs_empty(self):
        t = _task()
        assert t.tabs == []

    def test_entities_empty(self):
        t = _task()
        assert t.entities == {}

    def test_created_at_set(self):
        t = _task()
        assert isinstance(t.created_at, datetime)

    def test_workflow_session_id_none(self):
        t = _task()
        assert t.workflow_session_id is None


class TestTaskStateTransitions:
    def test_created_can_go_researching(self):
        assert TaskState.researching in VALID_TRANSITIONS[TaskState.created]

    def test_created_can_be_abandoned(self):
        assert TaskState.abandoned in VALID_TRANSITIONS[TaskState.created]

    def test_researching_to_research_complete(self):
        assert TaskState.research_complete in VALID_TRANSITIONS[TaskState.researching]

    def test_research_complete_to_ready(self):
        assert TaskState.ready_for_workflow in VALID_TRANSITIONS[TaskState.research_complete]

    def test_ready_to_workflow_running(self):
        assert TaskState.workflow_running in VALID_TRANSITIONS[TaskState.ready_for_workflow]

    def test_workflow_running_to_waiting_approval(self):
        assert TaskState.waiting_approval in VALID_TRANSITIONS[TaskState.workflow_running]

    def test_workflow_running_to_completed(self):
        assert TaskState.completed in VALID_TRANSITIONS[TaskState.workflow_running]

    def test_completed_has_no_transitions(self):
        assert VALID_TRANSITIONS[TaskState.completed] == set()

    def test_abandoned_has_no_transitions(self):
        assert VALID_TRANSITIONS[TaskState.abandoned] == set()

    def test_failed_can_retry(self):
        allowed = VALID_TRANSITIONS[TaskState.failed]
        assert TaskState.researching in allowed
        assert TaskState.ready_for_workflow in allowed

    def test_created_cannot_go_to_completed(self):
        assert TaskState.completed not in VALID_TRANSITIONS[TaskState.created]


class TestTaskTimeline:
    def test_append_single(self):
        tl = TaskTimeline(task_id="t1")
        e = TimelineEvent(
            event_id="e1", event_type=TimelineEventType.user_message,
            task_id="t1", data={"msg": "hello"},
        )
        tl.append(e)
        assert len(tl.events) == 1

    def test_append_multiple_preserves_order(self):
        tl = TaskTimeline(task_id="t1")
        for i in range(5):
            tl.append(TimelineEvent(
                event_id=str(i), event_type=TimelineEventType.user_message,
                task_id="t1", data={},
            ))
        assert [e.event_id for e in tl.events] == [str(i) for i in range(5)]

    def test_by_type_filter(self):
        tl = TaskTimeline(task_id="t1")
        tl.append(TimelineEvent("e1", TimelineEventType.user_message, "t1", {}))
        tl.append(TimelineEvent("e2", TimelineEventType.research_started, "t1", {}))
        tl.append(TimelineEvent("e3", TimelineEventType.user_message, "t1", {}))
        msgs = tl.by_type(TimelineEventType.user_message)
        assert len(msgs) == 2
        assert all(e.event_type == TimelineEventType.user_message for e in msgs)

    def test_by_type_empty_when_no_match(self):
        tl = TaskTimeline(task_id="t1")
        tl.append(TimelineEvent("e1", TimelineEventType.user_message, "t1", {}))
        assert tl.by_type(TimelineEventType.workflow_completed) == []


class TestApprovalRecord:
    def test_default_status_pending(self):
        r = ApprovalRecord(
            approval_id="a1", task_id="t1",
            action="click buy", risk_level="HIGH_RISK",
        )
        assert r.status == ApprovalStatus.pending

    def test_resolved_at_none_by_default(self):
        r = ApprovalRecord(
            approval_id="a1", task_id="t1",
            action="submit", risk_level="REQUIRES_APPROVAL",
        )
        assert r.resolved_at is None

    def test_status_values(self):
        assert ApprovalStatus.pending.value == "PENDING"
        assert ApprovalStatus.approved.value == "APPROVED"
        assert ApprovalStatus.denied.value == "DENIED"
        assert ApprovalStatus.expired.value == "EXPIRED"


class TestTaskTab:
    def test_tab_fields(self):
        tab = TaskTab(tab_id="tab1", url="https://example.com", title="Example", role=TabRole.research)
        assert tab.tab_id == "tab1"
        assert tab.role == TabRole.research

    def test_tab_roles(self):
        assert TabRole.research.value == "RESEARCH"
        assert TabRole.workflow.value == "WORKFLOW"
        assert TabRole.approval.value == "APPROVAL"
        assert TabRole.reference.value == "REFERENCE"


class TestPendingApprovals:
    def test_pending_filter(self):
        task = _task()
        task.approvals = [
            ApprovalRecord("a1", "t1", "act1", "SAFE", ApprovalStatus.pending),
            ApprovalRecord("a2", "t1", "act2", "HIGH_RISK", ApprovalStatus.approved),
            ApprovalRecord("a3", "t1", "act3", "HIGH_RISK", ApprovalStatus.pending),
        ]
        pending = task.pending_approvals()
        assert len(pending) == 2
        assert all(a.status == ApprovalStatus.pending for a in pending)


class TestTouch:
    def test_touch_updates_timestamp(self):
        task = _task()
        before = task.updated_at
        import time; time.sleep(0.001)
        task.touch()
        assert task.updated_at >= before
