"""
V4.5 Unified Task Graph — TaskLifecycleManager.

Validates and applies state transitions, records history, and emits
timeline events when state changes.

Rules:
  Research complete  → READY_FOR_WORKFLOW
  Workflow started   → WORKFLOW_RUNNING
  Approval required  → WAITING_APPROVAL
  Workflow success   → COMPLETED
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.unified.models import (
    UnifiedTask, TaskState, TimelineEvent, TimelineEventType, VALID_TRANSITIONS,
)
from app.unified import store as task_store


class TaskLifecycleError(Exception):
    """Raised when an invalid state transition is attempted."""


class TaskLifecycleManager:
    """Manages UnifiedTask creation and state transitions."""

    # ── Factory ───────────────────────────────────────────────────────────────

    def create(
        self,
        conversation_id: str,
        original_query: str,
        cognitive_session_id: Optional[str] = None,
    ) -> UnifiedTask:
        """Create a new UnifiedTask in CREATED state and register it in the store."""
        task_id = str(uuid.uuid4())[:8]
        task = UnifiedTask(
            task_id=task_id,
            conversation_id=conversation_id,
            original_query=original_query,
            cognitive_session_id=cognitive_session_id or conversation_id,
            state=TaskState.created,
        )
        self._append_event(task, TimelineEventType.user_message, {
            "query": original_query,
        })
        task_store.put(task)
        return task

    def get_or_create(
        self,
        conversation_id: str,
        original_query: str = "",
        cognitive_session_id: Optional[str] = None,
    ) -> UnifiedTask:
        """Return the task for this conversation or create one."""
        existing = task_store.get_by_conversation(conversation_id)
        if existing is not None:
            return existing
        return self.create(
            conversation_id=conversation_id,
            original_query=original_query,
            cognitive_session_id=cognitive_session_id,
        )

    # ── Transitions ───────────────────────────────────────────────────────────

    def transition(
        self,
        task: UnifiedTask,
        to_state: TaskState,
        data: Optional[dict] = None,
    ) -> None:
        """
        Apply a validated state transition.
        Raises TaskLifecycleError if the transition is not allowed.
        """
        allowed = VALID_TRANSITIONS.get(task.state, set())
        if to_state not in allowed:
            raise TaskLifecycleError(
                f"Invalid transition {task.state.value} → {to_state.value} "
                f"for task {task.task_id}"
            )
        task.state = to_state
        task.state_history.append((to_state, datetime.utcnow()))
        task.touch()

        event_type = _STATE_EVENT_MAP.get(to_state)
        if event_type:
            self._append_event(task, event_type, data or {})

        task_store.put(task)

        # V4.6: persist state change + snapshot at key milestones
        try:
            from app.unified import persistence as task_persistence
            from app.unified import timeline_persistence, snapshot as task_snapshot
            task_persistence.save(task)
            _SNAPSHOT_STATES = {
                TaskState.research_complete, TaskState.ready_for_workflow,
                TaskState.workflow_running, TaskState.completed,
            }
            if to_state in _SNAPSHOT_STATES:
                trigger_map = {
                    TaskState.research_complete:   "research_complete",
                    TaskState.ready_for_workflow:  "workflow_prepared",
                    TaskState.workflow_running:    "workflow_started",
                    TaskState.completed:           "workflow_completed",
                }
                trigger = trigger_map.get(to_state)
                if trigger:
                    task_snapshot.create(task, trigger)
        except Exception:
            pass  # persistence failure never blocks task lifecycle

    def mark_researching(self, task: UnifiedTask, topic: str) -> None:
        self.transition(task, TaskState.researching, {"topic": topic})

    def mark_research_complete(
        self,
        task: UnifiedTask,
        research_session_id: str,
        topic: str,
        opportunity_detected: bool = False,
    ) -> None:
        task.research_session_id = research_session_id
        self.transition(task, TaskState.research_complete, {
            "research_session_id": research_session_id,
            "topic": topic,
            "opportunity_detected": opportunity_detected,
        })
        # Auto-promote if intelligence detected an opportunity
        if opportunity_detected:
            self.transition(task, TaskState.ready_for_workflow, {
                "reason": "intelligence_layer_opportunity_detected",
            })

    def mark_workflow_started(self, task: UnifiedTask, workflow_session_id: str) -> None:
        task.workflow_session_id = workflow_session_id
        self.transition(task, TaskState.workflow_running, {
            "workflow_session_id": workflow_session_id,
        })

    def mark_waiting_approval(self, task: UnifiedTask, approval_id: str, action: str) -> None:
        self.transition(task, TaskState.waiting_approval, {
            "approval_id": approval_id,
            "action": action,
        })

    def mark_completed(self, task: UnifiedTask, summary: str = "") -> None:
        self.transition(task, TaskState.completed, {"summary": summary})

    def mark_failed(self, task: UnifiedTask, reason: str) -> None:
        self.transition(task, TaskState.failed, {"reason": reason})

    def mark_abandoned(self, task: UnifiedTask, reason: str = "") -> None:
        self.transition(task, TaskState.abandoned, {"reason": reason})

    # ── Timeline helper ───────────────────────────────────────────────────────

    def _append_event(
        self,
        task: UnifiedTask,
        event_type: TimelineEventType,
        data: dict,
    ) -> None:
        event = TimelineEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type=event_type,
            task_id=task.task_id,
            data=data,
        )
        task.timeline.append(event)
        # V4.6: persist the event
        try:
            from app.unified import timeline_persistence
            timeline_persistence.save_event(event)
        except Exception:
            pass


# Map task states to their timeline event equivalents
_STATE_EVENT_MAP: dict[TaskState, TimelineEventType] = {
    TaskState.researching:       TimelineEventType.research_started,
    TaskState.research_complete: TimelineEventType.research_completed,
    TaskState.ready_for_workflow: TimelineEventType.workflow_prepared,
    TaskState.workflow_running:  TimelineEventType.workflow_started,
    TaskState.waiting_approval:  TimelineEventType.approval_requested,
    TaskState.completed:         TimelineEventType.workflow_completed,
    TaskState.failed:            TimelineEventType.failure,
}


# Module-level singleton
_manager = TaskLifecycleManager()


def create(conversation_id: str, original_query: str = "", cognitive_session_id: Optional[str] = None) -> UnifiedTask:
    return _manager.create(conversation_id, original_query, cognitive_session_id)


def get_or_create(conversation_id: str, original_query: str = "", cognitive_session_id: Optional[str] = None) -> UnifiedTask:
    return _manager.get_or_create(conversation_id, original_query, cognitive_session_id)


def transition(task: UnifiedTask, to_state: TaskState, data: Optional[dict] = None) -> None:
    _manager.transition(task, to_state, data)


def mark_researching(task: UnifiedTask, topic: str) -> None:
    _manager.mark_researching(task, topic)


def mark_research_complete(task: UnifiedTask, research_session_id: str, topic: str, opportunity_detected: bool = False) -> None:
    _manager.mark_research_complete(task, research_session_id, topic, opportunity_detected)


def mark_workflow_started(task: UnifiedTask, workflow_session_id: str) -> None:
    _manager.mark_workflow_started(task, workflow_session_id)


def mark_waiting_approval(task: UnifiedTask, approval_id: str, action: str) -> None:
    _manager.mark_waiting_approval(task, approval_id, action)


def mark_completed(task: UnifiedTask, summary: str = "") -> None:
    _manager.mark_completed(task, summary)


def mark_failed(task: UnifiedTask, reason: str) -> None:
    _manager.mark_failed(task, reason)


def mark_abandoned(task: UnifiedTask, reason: str = "") -> None:
    _manager.mark_abandoned(task, reason)
