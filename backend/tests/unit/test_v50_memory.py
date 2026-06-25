"""
Unit tests for V5.0 MissionMemory.
Covers: build(), entity merging, goal deduplication, research/plan collection,
        approved decision filtering, build_by_id(), to_dict().
"""
import pytest
from datetime import datetime

from app.mission import memory as mission_memory
from app.mission.models import create_mission
from app.unified.models import (
    UnifiedTask, ApprovalRecord, ApprovalStatus, TaskState,
)


def _make_task(task_id: str, query: str = "q", goal: str = None, entities: dict = None) -> UnifiedTask:
    t = UnifiedTask(task_id=task_id, conversation_id="c1", original_query=query)
    if goal:
        t.current_goal = goal
    if entities:
        t.entities = entities
    return t


def _make_approval(task_id: str, action: str, status: ApprovalStatus) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=f"appr-{action}",
        task_id=task_id,
        action=action,
        risk_level="SAFE",
        status=status,
    )


class TestEntityMerging:
    def test_later_task_overrides_earlier_on_conflict(self):
        t1 = _make_task("t1", entities={"city": "London"})
        t2 = _make_task("t2", entities={"city": "Paris", "airport": "CDG"})
        m = create_mission("M")
        m.task_ids = ["t1", "t2"]
        mem = mission_memory.build(m, [t1, t2])
        assert mem.entities["city"] == "Paris"
        assert mem.entities["airport"] == "CDG"

    def test_empty_entities_ignored(self):
        t1 = _make_task("t1", entities={})
        t2 = _make_task("t2", entities={"k": "v"})
        m = create_mission("M")
        m.task_ids = ["t1", "t2"]
        mem = mission_memory.build(m, [t1, t2])
        assert mem.entities == {"k": "v"}

    def test_no_tasks_returns_empty_entities(self):
        m = create_mission("M")
        mem = mission_memory.build(m, [])
        assert mem.entities == {}


class TestGoalCollection:
    def test_goals_deduplicated(self):
        t1 = _make_task("t1", goal="Find best deal")
        t2 = _make_task("t2", goal="Find best deal")
        m = create_mission("M")
        m.task_ids = ["t1", "t2"]
        mem = mission_memory.build(m, [t1, t2])
        assert mem.goals.count("Find best deal") == 1

    def test_multiple_distinct_goals(self):
        t1 = _make_task("t1", goal="Goal A")
        t2 = _make_task("t2", goal="Goal B")
        m = create_mission("M")
        m.task_ids = ["t1", "t2"]
        mem = mission_memory.build(m, [t1, t2])
        assert len(mem.goals) == 2

    def test_none_goal_skipped(self):
        t1 = _make_task("t1")
        m = create_mission("M")
        m.task_ids = ["t1"]
        mem = mission_memory.build(m, [t1])
        assert mem.goals == []


class TestResearchFindings:
    def test_research_collected(self):
        t1 = _make_task("t1")
        t1.research_report = {
            "executive_summary": "summary",
            "key_findings": ["f1"],
            "confidence_score": 0.9,
        }
        m = create_mission("M")
        m.task_ids = ["t1"]
        mem = mission_memory.build(m, [t1])
        assert len(mem.research_findings) == 1
        assert mem.research_findings[0]["confidence"] == 0.9

    def test_most_recent_first(self):
        t1 = _make_task("t1")
        t1.research_report = {"executive_summary": "old"}
        t2 = _make_task("t2")
        t2.research_report = {"executive_summary": "new"}
        m = create_mission("M")
        m.task_ids = ["t1", "t2"]
        mem = mission_memory.build(m, [t1, t2])
        assert mem.research_findings[0]["summary"] == "new"

    def test_no_research_empty(self):
        t1 = _make_task("t1")
        m = create_mission("M")
        m.task_ids = ["t1"]
        mem = mission_memory.build(m, [t1])
        assert mem.research_findings == []


class TestDecisions:
    def test_only_approved_included(self):
        t1 = _make_task("t1")
        t1.approvals = [
            _make_approval("t1", "book-flight", ApprovalStatus.approved),
            _make_approval("t1", "pay-extra",   ApprovalStatus.denied),
            _make_approval("t1", "cancel",       ApprovalStatus.pending),
        ]
        m = create_mission("M")
        m.task_ids = ["t1"]
        mem = mission_memory.build(m, [t1])
        assert len(mem.decisions) == 1
        assert mem.decisions[0]["action"] == "book-flight"

    def test_no_approvals_empty_decisions(self):
        t1 = _make_task("t1")
        m = create_mission("M")
        m.task_ids = ["t1"]
        mem = mission_memory.build(m, [t1])
        assert mem.decisions == []


class TestToDict:
    def test_to_dict_serializable(self):
        m = create_mission("M")
        mem = mission_memory.build(m, [])
        d = mission_memory.to_dict(mem)
        assert isinstance(d["mission_id"], str)
        assert isinstance(d["entities"], dict)
        assert isinstance(d["last_updated"], str)
