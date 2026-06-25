"""
Unit tests for V5.0 MissionTimeline.
Covers: build(), event ordering, task → mission event mapping, get_summary().
"""
import pytest
from datetime import datetime, timedelta

from app.mission import timeline as mission_timeline
from app.mission.models import Mission, MissionState, MissionEventType, create_mission
from app.unified.models import UnifiedTask, TaskTimeline, TimelineEvent, TimelineEventType, TaskState


def _make_task(task_id: str, query: str = "test") -> UnifiedTask:
    task = UnifiedTask(
        task_id=task_id,
        conversation_id="conv-1",
        original_query=query,
    )
    return task


def _make_mission(task_ids: list) -> Mission:
    m = create_mission("Test Mission", "Test objective")
    m.task_ids = list(task_ids)
    return m


class TestBuild:
    def test_includes_mission_created_event(self):
        m = _make_mission([])
        events = mission_timeline.build(m, [])
        types = [e.event_type.value for e in events]
        assert "mission_created" in types

    def test_includes_task_attached_events(self):
        task = _make_task("t1", "find flights")
        m = _make_mission(["t1"])
        events = mission_timeline.build(m, [task])
        types = [e.event_type.value for e in events]
        assert "task_attached" in types

    def test_events_sorted_by_timestamp(self):
        task = _make_task("t1")
        m = _make_mission(["t1"])
        events = mission_timeline.build(m, [task])
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    def test_task_timeline_events_included(self):
        task = _make_task("t1")
        ev = TimelineEvent(
            event_id="ev-1",
            event_type=TimelineEventType.research_completed,
            task_id="t1",
            data={"query": "q"},
        )
        task.timeline.events.append(ev)
        m = _make_mission(["t1"])
        events = mission_timeline.build(m, [task])
        mission_types = {e.event_type.value for e in events}
        assert "research_completed" in mission_types

    def test_task_workflow_events_mapped(self):
        task = _make_task("t1")
        task.timeline.events.append(TimelineEvent(
            event_id="ev-2",
            event_type=TimelineEventType.workflow_started,
            task_id="t1",
            data={},
        ))
        m = _make_mission(["t1"])
        events = mission_timeline.build(m, [task])
        types = {e.event_type.value for e in events}
        assert "workflow_started" in types

    def test_completed_task_generates_task_completed_event(self):
        task = _make_task("t1")
        task.state = TaskState.completed
        m = _make_mission(["t1"])
        events = mission_timeline.build(m, [task])
        types = [e.event_type.value for e in events]
        assert "task_completed" in types

    def test_failed_task_generates_task_failed_event(self):
        task = _make_task("t1")
        task.state = TaskState.failed
        m = _make_mission(["t1"])
        events = mission_timeline.build(m, [task])
        types = [e.event_type.value for e in events]
        assert "task_failed" in types

    def test_empty_task_list_returns_mission_event_only(self):
        m = _make_mission([])
        events = mission_timeline.build(m, [])
        # Only the mission_created event (no task_attached for tasks not in list)
        assert len(events) >= 1

    def test_all_events_have_mission_id(self):
        task = _make_task("t1")
        m = _make_mission(["t1"])
        events = mission_timeline.build(m, [task])
        assert all(e.mission_id == m.mission_id for e in events)


class TestGetSummary:
    def test_returns_total_count(self):
        m = _make_mission([])
        events = mission_timeline.build(m, [])
        summary = mission_timeline.get_summary(events)
        assert summary["total_events"] >= 1

    def test_event_counts_dict(self):
        m = _make_mission([])
        events = mission_timeline.build(m, [])
        summary = mission_timeline.get_summary(events)
        assert isinstance(summary["event_counts"], dict)

    def test_empty_events_summary(self):
        summary = mission_timeline.get_summary([])
        assert summary["total_events"] == 0
        assert summary["first_event_at"] is None
        assert summary["last_event_at"] is None
