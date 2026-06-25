"""
V5.5 Unit tests — MissionReadinessScorer (24 tests).
"""
import pytest

from app.mission.intelligence.readiness_scorer import compute, score_from_context
from app.mission.intelligence.models import MissionAdvisoryState


class TestComputeFunction:
    """Tests for the pure compute() function."""

    def test_no_tasks_returns_zero(self):
        score = compute(0, 0, 0, False, False, False, 0, 0)
        assert score == 0.0

    def test_no_tasks_with_research_returns_small_nonzero(self):
        score = compute(0, 0, 0, True, False, False, 0, 0)
        assert score == 0.05

    def test_all_completed_with_research_and_plan(self):
        score = compute(3, 3, 0, True, True, True, 0, 0)
        assert score >= 0.80

    def test_partial_completion_with_research(self):
        score = compute(4, 1, 0, True, False, False, 0, 0)
        assert 0.10 < score < 0.50

    def test_single_completed_task_no_research(self):
        score = compute(1, 1, 0, False, False, False, 0, 0)
        assert 0.0 < score < 0.70

    def test_failed_tasks_reduce_score(self):
        base  = compute(3, 2, 0, True, False, False, 0, 0)
        failed = compute(3, 2, 1, True, False, False, 0, 0)
        assert failed < base

    def test_blockers_reduce_score(self):
        no_block  = compute(2, 2, 0, True, True, False, 0, 0)
        with_block = compute(2, 2, 0, True, True, False, 3, 0)
        assert with_block < no_block

    def test_missing_info_reduces_score(self):
        no_miss  = compute(2, 2, 0, True, True, False, 0, 0)
        with_miss = compute(2, 2, 0, True, True, False, 0, 4)
        assert with_miss < no_miss

    def test_plan_bonus_adds_to_score(self):
        no_plan   = compute(2, 2, 0, True, False, False, 0, 0)
        with_plan = compute(2, 2, 0, True, True, False, 0, 0)
        assert with_plan > no_plan

    def test_decisions_bonus_adds_to_score(self):
        no_dec   = compute(2, 2, 0, True, True, False, 0, 0)
        with_dec = compute(2, 2, 0, True, True, True, 0, 0)
        assert with_dec > no_dec

    def test_score_never_exceeds_one(self):
        score = compute(1, 1, 0, True, True, True, 0, 0)
        assert score <= 1.0

    def test_score_never_below_zero(self):
        score = compute(1, 0, 5, False, False, False, 10, 10)
        assert score >= 0.0

    def test_score_is_monotonically_increasing_with_completion(self):
        s1 = compute(4, 1, 0, True, False, False, 0, 0)
        s2 = compute(4, 2, 0, True, False, False, 0, 0)
        s3 = compute(4, 3, 0, True, False, False, 0, 0)
        s4 = compute(4, 4, 0, True, False, False, 0, 0)
        assert s1 < s2 < s3 < s4

    def test_research_bonus_applied_regardless_of_completion(self):
        without = compute(1, 0, 0, False, False, False, 0, 0)
        with_r  = compute(1, 0, 0, True, False, False, 0, 0)
        assert with_r > without

    def test_multiple_blockers_cap_at_max_penalty(self):
        one_blocker = compute(4, 4, 0, True, True, False, 1, 0)
        ten_blockers = compute(4, 4, 0, True, True, False, 10, 0)
        # Both penalised but ten should be at the floor (penalty capped at 0.30)
        assert ten_blockers < one_blocker

    def test_score_rounded_to_3_decimal_places(self):
        score = compute(3, 2, 0, True, False, False, 0, 0)
        assert score == round(score, 3)

    def test_zero_completion_no_research_no_plan(self):
        score = compute(5, 0, 0, False, False, False, 0, 0)
        assert score == 0.0

    def test_full_completion_no_research(self):
        score = compute(2, 2, 0, False, False, False, 0, 0)
        # 0.60 base, no bonuses
        assert abs(score - 0.60) < 0.01


class TestScoreFromContext:
    """Tests for score_from_context() with MissionContext."""

    def _make_ctx(self, task_summaries, entities=None, goals=None, approvals=None, memory=None):
        from app.mission.context_registry import MissionContext
        from app.mission.models import MissionMemory
        from datetime import datetime
        if memory is None:
            memory = MissionMemory(
                mission_id="m1",
                entities=entities or {},
                goals=goals or [],
                research_findings=[],
                execution_plans=[],
                decisions=[],
                last_updated=datetime.utcnow(),
            )
        return MissionContext(
            mission_id="m1",
            mission_title="Test Mission",
            mission_state="ACTIVE",
            priority=3,
            task_count=len(task_summaries),
            task_summaries=task_summaries,
            entities=entities or {},
            goals=goals or [],
            research_findings=[],
            execution_plans=[],
            approvals=approvals or [],
            memory=memory,
            latency_ms=0,
        )

    def test_empty_mission_score_zero(self):
        ctx = self._make_ctx([])
        detail = score_from_context(ctx)
        assert detail.score == 0.0
        assert detail.total_tasks == 0

    def test_one_completed_task_with_research_and_plan(self):
        ctx = self._make_ctx([
            {"task_id": "t1", "state": "COMPLETED", "query": "q", "goal": "g",
             "has_research": True, "has_plan": True, "approval_count": 0}
        ])
        detail = score_from_context(ctx)
        assert detail.score > 0.60
        assert detail.has_research is True
        assert detail.has_execution_plan is True

    def test_detail_completion_rate(self):
        ctx = self._make_ctx([
            {"task_id": "t1", "state": "COMPLETED", "query": "q", "goal": "g",
             "has_research": False, "has_plan": False, "approval_count": 0},
            {"task_id": "t2", "state": "RESEARCHING", "query": "q", "goal": "g",
             "has_research": False, "has_plan": False, "approval_count": 0},
        ])
        detail = score_from_context(ctx)
        assert detail.completion_rate == 0.5

    def test_failed_tasks_captured_in_detail(self):
        ctx = self._make_ctx([
            {"task_id": "t1", "state": "FAILED", "query": "q", "goal": None,
             "has_research": False, "has_plan": False, "approval_count": 0},
        ])
        detail = score_from_context(ctx)
        assert detail.failed_tasks == 1
        assert detail.score < 0.30

    def test_blocker_count_passed_through(self):
        ctx = self._make_ctx([
            {"task_id": "t1", "state": "COMPLETED", "query": "q", "goal": "g",
             "has_research": True, "has_plan": True, "approval_count": 0},
        ])
        detail_no_blockers   = score_from_context(ctx, blocker_count=0)
        detail_with_blockers = score_from_context(ctx, blocker_count=3)
        assert detail_with_blockers.score < detail_no_blockers.score

    def test_missing_info_count_passed_through(self):
        ctx = self._make_ctx([
            {"task_id": "t1", "state": "COMPLETED", "query": "q", "goal": "g",
             "has_research": True, "has_plan": True, "approval_count": 0},
        ])
        d0 = score_from_context(ctx, missing_info_count=0)
        d4 = score_from_context(ctx, missing_info_count=4)
        assert d4.score < d0.score
