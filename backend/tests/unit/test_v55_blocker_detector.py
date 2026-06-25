"""
V5.5 Unit tests — MissionBlockerDetector (22 tests).
"""
import pytest

from app.mission.intelligence import blocker_detector
from app.mission.intelligence.models import BlockerSeverity


def _ctx(task_summaries=None, approvals=None):
    """Build a minimal MissionContext for blocker testing."""
    from app.mission.context_registry import MissionContext
    from app.mission.models import MissionMemory
    from datetime import datetime

    mem = MissionMemory(
        mission_id="m1",
        entities={},
        goals=[],
        research_findings=[],
        execution_plans=[],
        decisions=[],
        last_updated=datetime.utcnow(),
    )
    summaries = task_summaries or []
    return MissionContext(
        mission_id="m1",
        mission_title="Buy MacBook",
        mission_state="ACTIVE",
        priority=3,
        task_count=len(summaries),
        task_summaries=summaries,
        entities={},
        goals=[],
        research_findings=[],
        execution_plans=[],
        approvals=approvals or [],
        memory=mem,
        latency_ms=0,
    )


def _ts(task_id="t1", state="COMPLETED", has_research=True, has_plan=False, approval_count=0):
    return {
        "task_id": task_id, "state": state, "query": "q", "goal": "g",
        "has_research": has_research, "has_plan": has_plan,
        "approval_count": approval_count,
    }


class TestNoTasks:
    def test_no_tasks_returns_no_tasks_blocker(self):
        blockers = blocker_detector.detect(_ctx([]))
        codes = [b.code for b in blockers]
        assert "NO_TASKS" in codes

    def test_no_tasks_is_critical(self):
        blockers = blocker_detector.detect(_ctx([]))
        critical = [b for b in blockers if b.code == "NO_TASKS"]
        assert critical[0].severity == BlockerSeverity.critical

    def test_no_tasks_returns_only_that_blocker(self):
        blockers = blocker_detector.detect(_ctx([]))
        assert len(blockers) == 1


class TestResearchBlocker:
    def test_no_research_is_critical_blocker(self):
        ctx = _ctx([_ts(has_research=False, has_plan=False)])
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "NO_RESEARCH" in codes

    def test_has_research_clears_no_research_blocker(self):
        ctx = _ctx([_ts(has_research=True)])
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "NO_RESEARCH" not in codes

    def test_no_research_severity_is_critical(self):
        ctx = _ctx([_ts(has_research=False)])
        blockers = blocker_detector.detect(ctx)
        nr = next(b for b in blockers if b.code == "NO_RESEARCH")
        assert nr.severity == BlockerSeverity.critical


class TestFailedTasksBlocker:
    def test_failed_task_adds_blocker(self):
        ctx = _ctx([_ts("t1", state="FAILED", has_research=True)])
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "FAILED_TASK" in codes

    def test_failed_task_is_critical(self):
        ctx = _ctx([_ts("t1", state="FAILED", has_research=True)])
        blockers = blocker_detector.detect(ctx)
        ft = next(b for b in blockers if b.code == "FAILED_TASK")
        assert ft.severity == BlockerSeverity.critical

    def test_failed_task_references_task_id(self):
        ctx = _ctx([_ts("mytask", state="FAILED", has_research=True)])
        blockers = blocker_detector.detect(ctx)
        ft = next(b for b in blockers if b.code == "FAILED_TASK")
        assert ft.task_id == "mytask"

    def test_two_failed_tasks_add_two_blockers(self):
        ctx = _ctx([
            _ts("t1", state="FAILED", has_research=True),
            _ts("t2", state="FAILED", has_research=True),
        ])
        failed_blockers = [b for b in blocker_detector.detect(ctx) if b.code == "FAILED_TASK"]
        assert len(failed_blockers) == 2


class TestPendingApprovalsBlocker:
    def test_pending_approval_is_critical(self):
        approvals = [{"task_id": "t1", "action": "buy", "risk_level": "HIGH",
                      "status": "PENDING", "note": ""}]
        ctx = _ctx(
            [_ts("t1", state="COMPLETED", has_research=True, has_plan=True)],
            approvals=approvals,
        )
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "PENDING_APPROVALS" in codes

    def test_approved_status_does_not_trigger_blocker(self):
        approvals = [{"task_id": "t1", "action": "buy", "risk_level": "HIGH",
                      "status": "APPROVED", "note": "OK"}]
        ctx = _ctx(
            [_ts("t1", has_research=True, has_plan=True)],
            approvals=approvals,
        )
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "PENDING_APPROVALS" not in codes


class TestMissingComparisonBlocker:
    def test_single_research_source_triggers_warning(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True),
            _ts("t2", state="COMPLETED", has_research=False),
        ])
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "MISSING_COMPARISON" in codes

    def test_two_research_sources_no_comparison_warning(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True),
            _ts("t2", state="COMPLETED", has_research=True),
        ])
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "MISSING_COMPARISON" not in codes


class TestWorkflowNotReadyBlocker:
    def test_all_complete_no_plan_triggers_warning(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True, has_plan=False),
            _ts("t2", state="COMPLETED", has_research=True, has_plan=False),
        ])
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "WORKFLOW_NOT_READY" in codes

    def test_has_plan_clears_workflow_not_ready(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True, has_plan=True),
        ])
        blockers = blocker_detector.detect(ctx)
        codes = [b.code for b in blockers]
        assert "WORKFLOW_NOT_READY" not in codes


class TestNoBlockersCase:
    def test_ready_mission_has_no_blockers(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True, has_plan=True),
            _ts("t2", state="COMPLETED", has_research=True, has_plan=True),
        ])
        blockers = blocker_detector.detect(ctx)
        assert blockers == []
