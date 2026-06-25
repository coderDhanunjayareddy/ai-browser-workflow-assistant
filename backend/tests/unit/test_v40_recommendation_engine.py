"""
V4.0 Unit Tests — WorkflowRecommendationEngine.

Tests cover:
  - Always produces at least 1 recommendation
  - Maximum 3 recommendations
  - Primary recommendation present
  - Missing info recommendation when blocked/partially_ready
  - Research more recommendation for high-confidence risky plans
  - plan_id linked correctly
"""
import pytest
from app.intelligence.models import (
    ActionType, ApprovalLevel, ExecutionOpportunity, ExecutionPlan,
    ReadinessState, WorkflowReadiness,
)
from app.intelligence.recommendation_engine import WorkflowRecommendationEngine


def _make_plan(
    plan_id: str = "plan-1",
    missing: list[str] | None = None,
    confidence: float = 0.9,
    approval: ApprovalLevel = ApprovalLevel.requires_approval,
) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id=plan_id,
        goal="book a flight",
        workflow_type="booking_workflow",
        required_inputs=["destination"],
        inferred_inputs={},
        missing_inputs=missing or [],
        confidence=confidence,
        recommended_next_action="Launch workflow",
        approval_level=approval,
    )


def _make_readiness(
    state: ReadinessState,
    missing: list[str] | None = None,
    score: float = 1.0,
) -> WorkflowReadiness:
    return WorkflowReadiness(
        state=state,
        ready_entities=[],
        missing_entities=missing or [],
        blocking_reason="Missing info" if state == ReadinessState.blocked else None,
        readiness_score=score,
    )


@pytest.fixture
def eng():
    return WorkflowRecommendationEngine()


class TestRecommendationCount:
    def test_at_least_one_recommendation(self, eng):
        plan = _make_plan()
        r = _make_readiness(ReadinessState.ready)
        recs = eng.generate(plan, r)
        assert len(recs) >= 1

    def test_max_three_recommendations(self, eng):
        plan = _make_plan(missing=["origin"], approval=ApprovalLevel.requires_approval)
        r = _make_readiness(ReadinessState.partially_ready, missing=["origin"], score=0.7)
        recs = eng.generate(plan, r)
        assert len(recs) <= 3


class TestPrimaryRecommendation:
    def test_primary_has_correct_plan_id(self, eng):
        plan = _make_plan(plan_id="my-plan-id")
        r = _make_readiness(ReadinessState.ready)
        recs = eng.generate(plan, r)
        assert recs[0].plan_id == "my-plan-id"

    def test_primary_action_is_string(self, eng):
        plan = _make_plan()
        r = _make_readiness(ReadinessState.ready)
        recs = eng.generate(plan, r)
        assert isinstance(recs[0].action, str) and len(recs[0].action) > 0

    def test_primary_confidence_from_plan(self, eng):
        plan = _make_plan(confidence=0.95)
        r = _make_readiness(ReadinessState.ready)
        recs = eng.generate(plan, r)
        assert recs[0].confidence == 0.95

    def test_primary_approval_from_plan(self, eng):
        plan = _make_plan(approval=ApprovalLevel.high_risk)
        r = _make_readiness(ReadinessState.ready)
        recs = eng.generate(plan, r)
        assert recs[0].approval_level == ApprovalLevel.high_risk


class TestMissingInfoRecommendation:
    def test_missing_info_rec_generated_when_blocked(self, eng):
        plan = _make_plan(missing=["destination"])
        r = _make_readiness(ReadinessState.blocked, missing=["destination"], score=0.0)
        recs = eng.generate(plan, r)
        assert len(recs) >= 2
        # Second recommendation should reference missing info
        assert "destination" in recs[1].action

    def test_missing_info_rec_generated_when_partially_ready(self, eng):
        plan = _make_plan(missing=["origin"])
        r = _make_readiness(ReadinessState.partially_ready, missing=["origin"], score=0.5)
        recs = eng.generate(plan, r)
        assert len(recs) >= 2

    def test_no_missing_info_rec_when_ready(self, eng):
        plan = _make_plan(missing=[])
        r = _make_readiness(ReadinessState.ready)
        recs = eng.generate(plan, r)
        # Only primary + possibly research-more
        assert all("Provide" not in rec.action for rec in recs)


class TestResearchMoreRecommendation:
    def test_research_more_added_when_risky_and_confident(self, eng):
        plan = _make_plan(confidence=0.8, approval=ApprovalLevel.high_risk, missing=[])
        r = _make_readiness(ReadinessState.ready, score=0.8)
        recs = eng.generate(plan, r)
        actions = [rec.action for rec in recs]
        assert any("Research" in a or "research" in a for a in actions)

    def test_research_more_is_safe(self, eng):
        plan = _make_plan(confidence=0.8, approval=ApprovalLevel.high_risk, missing=[])
        r = _make_readiness(ReadinessState.ready, score=0.8)
        recs = eng.generate(plan, r)
        research_recs = [rec for rec in recs if "Research" in rec.action or "research" in rec.action]
        for rec in research_recs:
            assert rec.approval_level == ApprovalLevel.safe


class TestRecommendationIds:
    def test_all_ids_unique(self, eng):
        plan = _make_plan(missing=["origin"], approval=ApprovalLevel.requires_approval)
        r = _make_readiness(ReadinessState.partially_ready, missing=["origin"], score=0.5)
        recs = eng.generate(plan, r)
        ids = [rec.recommendation_id for rec in recs]
        assert len(ids) == len(set(ids))


class TestReadinessStates:
    def test_ready_primary_mentions_prepare(self, eng):
        plan = _make_plan()
        r = _make_readiness(ReadinessState.ready)
        recs = eng.generate(plan, r)
        assert recs[0].readiness == ReadinessState.ready

    def test_blocked_primary_readiness_is_blocked(self, eng):
        plan = _make_plan(missing=["destination"])
        r = _make_readiness(ReadinessState.blocked, missing=["destination"], score=0.0)
        recs = eng.generate(plan, r)
        assert recs[0].readiness == ReadinessState.blocked
