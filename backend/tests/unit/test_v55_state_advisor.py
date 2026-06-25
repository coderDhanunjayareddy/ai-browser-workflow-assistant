"""
V5.5 Unit tests — MissionStateAdvisor (18 tests).

ADVISORY ONLY — these tests verify recommendation logic, not state mutation.
"""
import pytest

from app.mission.intelligence import state_advisor
from app.mission.intelligence.models import MissionAdvisoryState, MissionBlocker, BlockerSeverity


def _ctx(task_summaries=None):
    from app.mission.context_registry import MissionContext
    from app.mission.models import MissionMemory
    from datetime import datetime
    summaries = task_summaries or []
    mem = MissionMemory(
        mission_id="m1", entities={}, goals=[], research_findings=[],
        execution_plans=[], decisions=[], last_updated=datetime.utcnow(),
    )
    return MissionContext(
        mission_id="m1", mission_title="Test", mission_state="ACTIVE", priority=3,
        task_count=len(summaries), task_summaries=summaries,
        entities={}, goals=[], research_findings=[], execution_plans=[],
        approvals=[], memory=mem, latency_ms=0,
    )


def _ts(task_id="t1", state="COMPLETED"):
    return {"task_id": task_id, "state": state, "query": "q", "goal": None,
            "has_research": True, "has_plan": True, "approval_count": 0}


def _critical(code="BLOCKED"):
    return MissionBlocker(code=code, description="desc", severity=BlockerSeverity.critical)


def _warning(code="WARN"):
    return MissionBlocker(code=code, description="desc", severity=BlockerSeverity.warning)


class TestCompletedAdvisoryState:
    def test_all_tasks_complete_high_readiness_is_completed(self):
        ctx = _ctx([_ts("t1", "COMPLETED"), _ts("t2", "COMPLETED")])
        result = state_advisor.advise(ctx, [], 0.95)
        assert result == MissionAdvisoryState.completed

    def test_all_complete_but_low_readiness_is_not_completed(self):
        ctx = _ctx([_ts("t1", "COMPLETED")])
        result = state_advisor.advise(ctx, [], 0.70)
        assert result != MissionAdvisoryState.completed

    def test_completed_threshold_is_0_90(self):
        ctx = _ctx([_ts("t1", "COMPLETED")])
        just_below = state_advisor.advise(ctx, [], 0.89)
        at_threshold = state_advisor.advise(ctx, [], 0.90)
        assert just_below != MissionAdvisoryState.completed
        assert at_threshold == MissionAdvisoryState.completed


class TestBlockedAdvisoryState:
    def test_critical_blocker_returns_blocked(self):
        ctx = _ctx([_ts()])
        result = state_advisor.advise(ctx, [_critical()], 0.80)
        assert result == MissionAdvisoryState.blocked

    def test_failed_task_returns_blocked(self):
        ctx = _ctx([_ts("t1", "FAILED")])
        result = state_advisor.advise(ctx, [], 0.20)
        assert result == MissionAdvisoryState.blocked

    def test_warning_only_does_not_block(self):
        ctx = _ctx([_ts("t1", "COMPLETED")])
        result = state_advisor.advise(ctx, [_warning()], 0.80)
        assert result != MissionAdvisoryState.blocked

    def test_blocked_takes_precedence_over_completed(self):
        ctx = _ctx([_ts("t1", "COMPLETED")])
        result = state_advisor.advise(ctx, [_critical()], 0.95)
        assert result == MissionAdvisoryState.blocked


class TestReadyAdvisoryState:
    def test_high_readiness_no_blockers_is_ready(self):
        ctx = _ctx([_ts("t1", "COMPLETED"), _ts("t2", "RESEARCHING")])
        result = state_advisor.advise(ctx, [], 0.85)
        assert result == MissionAdvisoryState.ready

    def test_ready_threshold_is_0_80(self):
        ctx = _ctx([_ts("t1", "RESEARCHING")])
        just_below = state_advisor.advise(ctx, [], 0.79)
        at_threshold = state_advisor.advise(ctx, [], 0.80)
        assert just_below != MissionAdvisoryState.ready
        assert at_threshold == MissionAdvisoryState.ready


class TestPausedAdvisoryState:
    def test_all_terminal_mix_not_all_complete_is_paused(self):
        ctx = _ctx([
            _ts("t1", "COMPLETED"),
            _ts("t2", "ABANDONED"),
        ])
        result = state_advisor.advise(ctx, [], 0.40)
        assert result == MissionAdvisoryState.paused


class TestActiveAdvisoryState:
    def test_no_tasks_is_active(self):
        ctx = _ctx([])
        result = state_advisor.advise(ctx, [], 0.0)
        assert result == MissionAdvisoryState.active

    def test_tasks_in_progress_is_active(self):
        ctx = _ctx([_ts("t1", "RESEARCHING"), _ts("t2", "CREATED")])
        result = state_advisor.advise(ctx, [], 0.20)
        assert result == MissionAdvisoryState.active

    def test_mixed_active_and_done_is_active(self):
        ctx = _ctx([_ts("t1", "COMPLETED"), _ts("t2", "RESEARCHING")])
        result = state_advisor.advise(ctx, [], 0.50)
        assert result == MissionAdvisoryState.active


class TestAdvisoryStateDoesNotMutate:
    def test_advise_does_not_change_actual_mission_state(self):
        from app.mission.models import create_mission
        m = create_mission("Test")
        assert m.state.value == "CREATED"
        ctx = _ctx([_ts()])
        _ = state_advisor.advise(ctx, [], 0.90)
        assert m.state.value == "CREATED"  # unchanged
