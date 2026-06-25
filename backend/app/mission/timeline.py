"""
V5.0 Mission Layer — MissionTimeline.

Merges task-level timeline events into a mission-level chronological view.
NO new DB table — reads from existing TaskTimeline objects on UnifiedTask.

Mapping: TaskTimeline.TimelineEvent → MissionTimelineEvent
  task event types are prefixed with "task:" in the merged view
  mission-level events (mission_created, task_attached, etc.) are pure mission events
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.mission.models import Mission, MissionTimelineEvent, MissionEventType
from app.unified.models import UnifiedTask, TimelineEventType


# Mapping from task-level event types to mission event types
_TASK_TO_MISSION: dict[str, Optional[MissionEventType]] = {
    TimelineEventType.research_completed.value: MissionEventType.research_completed,
    TimelineEventType.workflow_started.value:   MissionEventType.workflow_started,
    TimelineEventType.workflow_completed.value:  MissionEventType.workflow_completed,
    TimelineEventType.approval_granted.value:   MissionEventType.approval_granted,
    TimelineEventType.approval_denied.value:    MissionEventType.approval_denied,
    # Others are retained as task-scoped but not promoted to mission events
}


def _make_id() -> str:
    return f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{str(uuid.uuid4())[:4]}"


def build(mission: Mission, tasks: list[UnifiedTask]) -> list[MissionTimelineEvent]:
    """
    Build a chronological mission timeline by merging all task timelines.

    Returns list of MissionTimelineEvent sorted by timestamp (oldest first).
    """
    events: list[MissionTimelineEvent] = []

    # 1. Mission creation event
    events.append(MissionTimelineEvent(
        event_id=_make_id(),
        event_type=MissionEventType.mission_created,
        mission_id=mission.mission_id,
        task_id=None,
        data={"title": mission.title, "objective": mission.objective},
        timestamp=mission.created_at,
    ))

    # 2. Synthetic task_attached events (based on task.created_at order)
    for task_id in mission.task_ids:
        task = next((t for t in tasks if t.task_id == task_id), None)
        events.append(MissionTimelineEvent(
            event_id=_make_id(),
            event_type=MissionEventType.task_attached,
            mission_id=mission.mission_id,
            task_id=task_id,
            data={"query": task.original_query if task else ""},
            timestamp=task.created_at if task else mission.created_at,
        ))

    # 3. Map task timeline events
    for task in tasks:
        for ev in task.timeline.events:
            mission_type = _TASK_TO_MISSION.get(ev.event_type.value)
            if mission_type is None:
                # Include all task events as generic mission events
                # using the raw event type value
                try:
                    mission_type = MissionEventType(ev.event_type.value)
                except ValueError:
                    # Custom or unknown event type — wrap as task_completed analogue
                    mission_type = MissionEventType.task_attached
            events.append(MissionTimelineEvent(
                event_id=ev.event_id,
                event_type=mission_type,
                mission_id=mission.mission_id,
                task_id=task.task_id,
                data={**ev.data, "_task_event_type": ev.event_type.value},
                timestamp=ev.timestamp,
            ))

    # 4. Task completion events
    for task in tasks:
        if task.state.value == "COMPLETED":
            events.append(MissionTimelineEvent(
                event_id=_make_id(),
                event_type=MissionEventType.task_completed,
                mission_id=mission.mission_id,
                task_id=task.task_id,
                data={"final_state": task.state.value},
                timestamp=task.updated_at,
            ))
        elif task.state.value == "FAILED":
            events.append(MissionTimelineEvent(
                event_id=_make_id(),
                event_type=MissionEventType.task_failed,
                mission_id=mission.mission_id,
                task_id=task.task_id,
                data={"final_state": task.state.value},
                timestamp=task.updated_at,
            ))

    # Sort by timestamp, then event_id (timestamp-prefixed) for determinism
    events.sort(key=lambda e: (e.timestamp, e.event_id))
    return events


def get_summary(events: list[MissionTimelineEvent]) -> dict:
    """Return a compact summary of a mission timeline."""
    from collections import Counter
    counts = Counter(e.event_type.value for e in events)
    return {
        "total_events":   len(events),
        "event_counts":   dict(counts),
        "first_event_at": events[0].timestamp.isoformat() if events else None,
        "last_event_at":  events[-1].timestamp.isoformat() if events else None,
    }
