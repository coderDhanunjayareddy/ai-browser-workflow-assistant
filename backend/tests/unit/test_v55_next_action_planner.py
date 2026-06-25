"""
V5.5 Unit tests — MissionNextActionPlanner (20 tests).
"""
import pytest

from app.mission.intelligence import next_action_planner
from app.mission.intelligence.models import MissionBlocker, BlockerSeverity


def _ctx(task_summaries=None, approvals=None, title="Buy MacBook"):
    from app.mission.context_registry import MissionContext
    from app.mission.models import MissionMemory
    from datetime import datetime
    summaries = task_summaries or []
    mem = MissionMemory(
        mission_id="m1", entities={}, goals=[], research_findings=[],
        execution_plans=[], decisions=[], last_updated=datetime.utcnow(),
    )
    return MissionContext(
        mission_id="m1", mission_title=title, mission_state="ACTIVE", priority=3,
        task_count=len(summaries), task_summaries=summaries,
        entities={}, goals=[], research_findings=[], execution_plans=[],
        approvals=approvals or [], memory=mem, latency_ms=0,
    )


def _ts(task_id="t1", state="COMPLETED", has_research=True, has_plan=False):
    return {"task_id": task_id, "state": state, "query": "q", "goal": None,
            "has_research": has_research, "has_plan": has_plan, "approval_count": 0}


def _critical(code, desc):
    return MissionBlocker(code=code, description=desc, severity=BlockerSeverity.critical)


def _warning(code, desc):
    return MissionBlocker(code=code, description=desc, severity=BlockerSeverity.warning)


class TestCriticalBlockerRule:
    def test_critical_blocker_returns_resolve_blocker(self):
        b = _critical("NO_RESEARCH", "No research found.")
        action = next_action_planner.plan(_ctx([_ts()]), [b], 0.3)
        assert action.action == "Resolve blocker"
        assert action.priority == 1

    def test_critical_blocker_reasoning_contains_description(self):
        b = _critical("NO_RESEARCH", "Must add research first.")
        action = next_action_planner.plan(_ctx([_ts()]), [b], 0.3)
        assert "Must add research first" in action.reasoning

    def test_multiple_blockers_uses_first_critical(self):
        b1 = _critical("NO_RESEARCH", "Desc1")
        b2 = _critical("FAILED_TASK", "Desc2")
        action = next_action_planner.plan(_ctx([_ts()]), [b1, b2], 0.2)
        assert action.action == "Resolve blocker"
        assert "Desc1" in action.reasoning  # first critical wins


class TestNoTasksRule:
    def test_no_tasks_recommends_attach_task(self):
        action = next_action_planner.plan(_ctx([]), [], 0.0)
        assert "research" in action.action.lower() or "attach" in action.action.lower()

    def test_no_tasks_priority_is_1(self):
        action = next_action_planner.plan(_ctx([]), [], 0.0)
        assert action.priority == 1


class TestPendingApprovalsRule:
    def test_pending_approval_recommends_review(self):
        ctx = _ctx(
            [_ts()],
            approvals=[{"task_id": "t1", "action": "buy", "risk_level": "HIGH",
                        "status": "PENDING", "note": ""}]
        )
        action = next_action_planner.plan(ctx, [], 0.5)
        assert "approval" in action.action.lower()
        assert action.priority == 1


class TestResearchRule:
    def test_no_research_and_no_active_tasks_recommends_start_research(self):
        ctx = _ctx([_ts("t1", state="COMPLETED", has_research=False)])
        action = next_action_planner.plan(ctx, [], 0.0)
        assert "research" in action.action.lower()

    def test_no_research_but_active_tasks_recommends_continue(self):
        ctx = _ctx([_ts("t1", state="RESEARCHING", has_research=False)])
        action = next_action_planner.plan(ctx, [], 0.0)
        assert "continue" in action.action.lower() or "research" in action.action.lower()


class TestCompareOptionsRule:
    def test_single_research_all_terminal_recommends_compare(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True),
            _ts("t2", state="COMPLETED", has_research=False),
        ])
        action = next_action_planner.plan(ctx, [], 0.40)
        assert "compare" in action.action.lower()
        assert action.priority == 2


class TestFailedTasksRule:
    def test_failed_task_recommends_retry(self):
        ctx = _ctx([_ts("t1", state="FAILED", has_research=True)])
        action = next_action_planner.plan(ctx, [], 0.1)
        assert "retry" in action.action.lower() or "failed" in action.action.lower() or "replace" in action.action.lower()


class TestPrepareWorkflowRule:
    def test_all_done_no_plan_recommends_prepare(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True, has_plan=False),
            _ts("t2", state="COMPLETED", has_research=True, has_plan=False),
        ])
        action = next_action_planner.plan(ctx, [], 0.70)
        assert "workflow" in action.action.lower() or "plan" in action.action.lower()
        assert action.priority == 2


class TestLaunchWorkflowRule:
    def test_ready_mission_recommends_open_workflow(self):
        ctx = _ctx([_ts("t1", has_research=True, has_plan=True)])
        action = next_action_planner.plan(ctx, [], 0.85)
        assert "workflow" in action.action.lower()
        assert action.priority == 1


class TestMonitorActiveRule:
    def test_active_tasks_recommend_monitor(self):
        ctx = _ctx([
            _ts("t1", state="COMPLETED", has_research=True, has_plan=False),
            _ts("t2", state="RESEARCHING", has_research=False, has_plan=False),
        ])
        action = next_action_planner.plan(ctx, [], 0.45)
        assert "monitor" in action.action.lower() or "progress" in action.action.lower() or "task" in action.action.lower()


class TestGeneralProperties:
    def test_action_is_non_empty_string(self):
        action = next_action_planner.plan(_ctx([_ts()]), [], 0.5)
        assert isinstance(action.action, str)
        assert len(action.action) > 0

    def test_reasoning_is_non_empty_string(self):
        action = next_action_planner.plan(_ctx([_ts()]), [], 0.5)
        assert isinstance(action.reasoning, str)
        assert len(action.reasoning) > 0

    def test_priority_is_int_between_1_and_3(self):
        action = next_action_planner.plan(_ctx([_ts()]), [], 0.5)
        assert action.priority in {1, 2, 3}
