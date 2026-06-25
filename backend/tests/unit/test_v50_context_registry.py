"""
Unit tests for V5.0 MissionContextRegistry.
Covers: get_context(), get_context_dict(), task summary building,
        aggregated approvals, latency field.
"""
import pytest

from app.mission import context_registry, store as mission_store
from app.mission import lifecycle as mission_lifecycle, analytics as mission_analytics
from app.mission.context_registry import get_context, get_context_dict
from app.unified import store as task_store
from app.unified.models import UnifiedTask, ApprovalRecord, ApprovalStatus


@pytest.fixture(autouse=True)
def reset():
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()


def _put_task(task_id: str, query: str = "test") -> UnifiedTask:
    task = UnifiedTask(task_id=task_id, conversation_id="c1", original_query=query)
    task_store.put(task)
    return task


class TestGetContext:
    def test_returns_none_for_unknown_mission(self):
        assert get_context("no-such-mission") is None

    def test_returns_context_for_existing_mission(self):
        m = mission_lifecycle.create_mission_obj("M", "obj")
        t1 = _put_task("t1", "test query")
        mission_lifecycle.attach_task(m.mission_id, "t1")
        ctx = get_context(m.mission_id)
        assert ctx is not None
        assert ctx.mission_id == m.mission_id

    def test_task_count_matches(self):
        m = mission_lifecycle.create_mission_obj("M")
        _put_task("t1")
        _put_task("t2")
        mission_lifecycle.attach_task(m.mission_id, "t1")
        mission_lifecycle.attach_task(m.mission_id, "t2")
        ctx = get_context(m.mission_id)
        assert ctx.task_count == 2

    def test_task_summaries_include_correct_fields(self):
        m = mission_lifecycle.create_mission_obj("M")
        t = _put_task("t1", "find flights")
        t.research_report = {"key": "value"}
        mission_lifecycle.attach_task(m.mission_id, "t1")
        ctx = get_context(m.mission_id)
        summary = ctx.task_summaries[0]
        assert summary["task_id"] == "t1"
        assert summary["has_research"] is True
        assert summary["has_plan"] is False

    def test_latency_ms_non_negative(self):
        m = mission_lifecycle.create_mission_obj("M")
        ctx = get_context(m.mission_id)
        assert ctx.latency_ms >= 0

    def test_empty_mission_empty_tasks(self):
        m = mission_lifecycle.create_mission_obj("M")
        ctx = get_context(m.mission_id)
        assert ctx.task_count == 0
        assert ctx.task_summaries == []

    def test_approvals_aggregated_from_all_tasks(self):
        m = mission_lifecycle.create_mission_obj("M")
        t1 = _put_task("ta1")
        t1.approvals.append(ApprovalRecord(
            approval_id="a1", task_id="ta1", action="pay", risk_level="SAFE",
            status=ApprovalStatus.approved,
        ))
        t2 = _put_task("ta2")
        t2.approvals.append(ApprovalRecord(
            approval_id="a2", task_id="ta2", action="confirm", risk_level="SAFE",
            status=ApprovalStatus.pending,
        ))
        mission_lifecycle.attach_task(m.mission_id, "ta1")
        mission_lifecycle.attach_task(m.mission_id, "ta2")
        ctx = get_context(m.mission_id)
        assert len(ctx.approvals) == 2


class TestGetContextDict:
    def test_returns_none_for_unknown(self):
        assert get_context_dict("ghost") is None

    def test_returns_serializable_dict(self):
        m = mission_lifecycle.create_mission_obj("M", "objective")
        d = get_context_dict(m.mission_id)
        assert isinstance(d, dict)
        assert "mission_id" in d
        assert "entities" in d
        assert "memory" in d

    def test_latency_in_dict(self):
        m = mission_lifecycle.create_mission_obj("M")
        d = get_context_dict(m.mission_id)
        assert isinstance(d["latency_ms"], int)
