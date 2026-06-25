"""
V4.5 Unified Task Graph — TaskTimelineManager.

Provides helpers for appending typed events to a task's timeline and
for reading back a sorted chronological view.

The timeline merges:
  - Conversation history (user_message, assistant_response)
  - Research timeline (research_started, research_completed)
  - Workflow timeline (workflow_started, workflow_completed)
  - Approval history (approval_requested, approval_granted, approval_denied)
  - Failures

All events are appended in real-time as they happen, so the timeline is
always chronologically ordered.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.unified.models import (
    UnifiedTask, TimelineEvent, TimelineEventType,
)
from app.unified import store as task_store


class TaskTimelineManager:
    """Append events to a task's unified timeline."""

    def append(
        self,
        task: UnifiedTask,
        event_type: TimelineEventType,
        data: dict,
        timestamp: Optional[datetime] = None,
    ) -> TimelineEvent:
        event = TimelineEvent(
            event_id=str(uuid.uuid4())[:8],
            event_type=event_type,
            task_id=task.task_id,
            data=data,
            timestamp=timestamp or datetime.utcnow(),
        )
        task.timeline.append(event)
        task.touch()
        task_store.put(task)
        return event

    # ── Typed helpers ─────────────────────────────────────────────────────────

    def record_user_message(self, task: UnifiedTask, message: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.user_message, {"message": message})

    def record_assistant_response(self, task: UnifiedTask, response_type: str, summary: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.assistant_response, {
            "type": response_type,
            "summary": summary[:200],
        })

    def record_research_started(self, task: UnifiedTask, topic: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.research_started, {"topic": topic})

    def record_research_completed(self, task: UnifiedTask, topic: str, confidence: float, source_count: int) -> TimelineEvent:
        return self.append(task, TimelineEventType.research_completed, {
            "topic": topic,
            "confidence": confidence,
            "source_count": source_count,
        })

    def record_workflow_prepared(self, task: UnifiedTask, workflow_type: str, approval_level: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.workflow_prepared, {
            "workflow_type": workflow_type,
            "approval_level": approval_level,
        })

    def record_workflow_started(self, task: UnifiedTask, session_id: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.workflow_started, {"session_id": session_id})

    def record_workflow_completed(self, task: UnifiedTask, steps_completed: int, success: bool) -> TimelineEvent:
        return self.append(task, TimelineEventType.workflow_completed, {
            "steps_completed": steps_completed,
            "success": success,
        })

    def record_approval_requested(self, task: UnifiedTask, action: str, risk_level: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.approval_requested, {
            "action": action,
            "risk_level": risk_level,
        })

    def record_approval_granted(self, task: UnifiedTask, action: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.approval_granted, {"action": action})

    def record_approval_denied(self, task: UnifiedTask, action: str, reason: str = "") -> TimelineEvent:
        return self.append(task, TimelineEventType.approval_denied, {
            "action": action,
            "reason": reason,
        })

    def record_failure(self, task: UnifiedTask, reason: str, stage: str) -> TimelineEvent:
        return self.append(task, TimelineEventType.failure, {
            "reason": reason,
            "stage": stage,
        })

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_ordered(self, task: UnifiedTask) -> list[TimelineEvent]:
        """Return timeline events sorted by timestamp ascending."""
        return sorted(task.timeline.events, key=lambda e: e.timestamp)

    def get_summary(self, task: UnifiedTask) -> list[dict]:
        """Return a lightweight dict representation for API serialization."""
        return [
            {
                "event_id": e.event_id,
                "type": e.event_type.value,
                "timestamp": e.timestamp.isoformat(),
                "data": e.data,
            }
            for e in self.get_ordered(task)
        ]


# Module-level singleton
_manager = TaskTimelineManager()


def append(task: UnifiedTask, event_type: TimelineEventType, data: dict, timestamp: Optional[datetime] = None) -> TimelineEvent:
    return _manager.append(task, event_type, data, timestamp)


def record_user_message(task: UnifiedTask, message: str) -> TimelineEvent:
    return _manager.record_user_message(task, message)


def record_assistant_response(task: UnifiedTask, response_type: str, summary: str) -> TimelineEvent:
    return _manager.record_assistant_response(task, response_type, summary)


def record_research_started(task: UnifiedTask, topic: str) -> TimelineEvent:
    return _manager.record_research_started(task, topic)


def record_research_completed(task: UnifiedTask, topic: str, confidence: float, source_count: int) -> TimelineEvent:
    return _manager.record_research_completed(task, topic, confidence, source_count)


def record_workflow_prepared(task: UnifiedTask, workflow_type: str, approval_level: str) -> TimelineEvent:
    return _manager.record_workflow_prepared(task, workflow_type, approval_level)


def record_workflow_started(task: UnifiedTask, session_id: str) -> TimelineEvent:
    return _manager.record_workflow_started(task, session_id)


def record_workflow_completed(task: UnifiedTask, steps_completed: int, success: bool) -> TimelineEvent:
    return _manager.record_workflow_completed(task, steps_completed, success)


def record_approval_requested(task: UnifiedTask, action: str, risk_level: str) -> TimelineEvent:
    return _manager.record_approval_requested(task, action, risk_level)


def record_approval_granted(task: UnifiedTask, action: str) -> TimelineEvent:
    return _manager.record_approval_granted(task, action)


def record_approval_denied(task: UnifiedTask, action: str, reason: str = "") -> TimelineEvent:
    return _manager.record_approval_denied(task, action, reason)


def record_failure(task: UnifiedTask, reason: str, stage: str) -> TimelineEvent:
    return _manager.record_failure(task, reason, stage)


def get_ordered(task: UnifiedTask) -> list[TimelineEvent]:
    return _manager.get_ordered(task)


def get_summary(task: UnifiedTask) -> list[dict]:
    return _manager.get_summary(task)
