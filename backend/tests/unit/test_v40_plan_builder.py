"""
V4.0 Unit Tests — ExecutionPlanBuilder.

Tests cover:
  - Plan fields populated correctly
  - workflow_type mapping per ActionType
  - inferred_inputs from cognitive session
  - missing_inputs when entities unavailable
  - confidence derived from readiness score
  - recommended_next_action text for each state
"""
import pytest
from app.intelligence.models import (
    ActionType, ApprovalLevel, ExecutionOpportunity,
    GoalTree, ReadinessState, WorkflowReadiness,
)
from app.intelligence.plan_builder import ExecutionPlanBuilder


def _make_opp(action_type: ActionType, required: list[str]) -> ExecutionOpportunity:
    return ExecutionOpportunity(
        detected=True,
        confidence=0.9,
        action_type=action_type,
        required_entities=required,
        missing_information=[],
        workflow_candidate=True,
        raw_action_keywords=[],
    )


def _make_readiness(
    state: ReadinessState,
    ready: list[str],
    missing: list[str],
    score: float,
    blocking_reason: str | None = None,
) -> WorkflowReadiness:
    return WorkflowReadiness(
        state=state,
        ready_entities=ready,
        missing_entities=missing,
        blocking_reason=blocking_reason,
        readiness_score=score,
    )


class _FakeEntity:
    def __init__(self, name, value=None):
        self.name = name
        self.aliases = []
        self.metadata = {"value": value or name}


class _FakeSession:
    def __init__(self, entity_names: list[str]):
        self.active_entities = {n: _FakeEntity(n) for n in entity_names}
        self.active_goal = None


@pytest.fixture
def bld():
    return ExecutionPlanBuilder()


class TestPlanFields:
    def test_plan_id_is_string(self, bld):
        opp = _make_opp(ActionType.book, ["destination"])
        r = _make_readiness(ReadinessState.blocked, [], ["destination"], 0.0, "Missing destination")
        plan = bld.build("book a flight", "flight", opp, r, ApprovalLevel.requires_approval)
        assert isinstance(plan.plan_id, str) and len(plan.plan_id) > 0

    def test_plan_goal_is_query(self, bld):
        opp = _make_opp(ActionType.book, [])
        r = _make_readiness(ReadinessState.ready, [], [], 1.0)
        plan = bld.build("book a flight to Mumbai", "flight to Mumbai", opp, r, ApprovalLevel.requires_approval)
        assert plan.goal == "book a flight to Mumbai"

    def test_workflow_type_book(self, bld):
        opp = _make_opp(ActionType.book, [])
        r = _make_readiness(ReadinessState.ready, [], [], 1.0)
        plan = bld.build("book", "flight", opp, r, ApprovalLevel.requires_approval)
        assert plan.workflow_type == "booking_workflow"

    def test_workflow_type_purchase(self, bld):
        opp = _make_opp(ActionType.purchase, [])
        r = _make_readiness(ReadinessState.ready, [], [], 1.0)
        plan = bld.build("buy", "laptop", opp, r, ApprovalLevel.high_risk)
        assert plan.workflow_type == "purchase_workflow"

    def test_workflow_type_register(self, bld):
        opp = _make_opp(ActionType.register, [])
        r = _make_readiness(ReadinessState.ready, [], [], 1.0)
        plan = bld.build("sign up", "newsletter", opp, r, ApprovalLevel.requires_approval)
        assert plan.workflow_type == "registration_workflow"


class TestInferredInputs:
    def test_inferred_inputs_from_session(self, bld):
        opp = _make_opp(ActionType.book, ["destination"])
        r = _make_readiness(ReadinessState.ready, ["destination"], [], 1.0)
        session = _FakeSession(["destination"])
        plan = bld.build("book flight", "flight", opp, r, ApprovalLevel.requires_approval, cognitive_session=session)
        assert "destination" in plan.inferred_inputs

    def test_missing_inputs_when_no_session(self, bld):
        opp = _make_opp(ActionType.book, ["destination", "date"])
        r = _make_readiness(ReadinessState.blocked, [], ["destination", "date"], 0.0, "Missing")
        plan = bld.build("book flight", "flight", opp, r, ApprovalLevel.requires_approval)
        assert "destination" in plan.missing_inputs
        assert "date" in plan.missing_inputs


class TestConfidence:
    def test_confidence_high_when_ready(self, bld):
        opp = _make_opp(ActionType.book, [])
        r = _make_readiness(ReadinessState.ready, [], [], 1.0)
        plan = bld.build("book", "t", opp, r, ApprovalLevel.requires_approval)
        assert plan.confidence >= 0.7

    def test_confidence_low_when_blocked(self, bld):
        opp = _make_opp(ActionType.book, ["destination"])
        r = _make_readiness(ReadinessState.blocked, [], ["destination"], 0.0, "x")
        plan = bld.build("book", "t", opp, r, ApprovalLevel.requires_approval)
        assert plan.confidence < 0.5

    def test_confidence_between_ready_and_blocked_when_partial(self, bld):
        opp = _make_opp(ActionType.book, ["origin", "destination"])
        r = _make_readiness(ReadinessState.partially_ready, ["destination"], ["origin"], 0.5)
        plan_ready = bld.build("b", "t", _make_opp(ActionType.book, []),
                               _make_readiness(ReadinessState.ready, [], [], 1.0),
                               ApprovalLevel.requires_approval)
        plan_partial = bld.build("book", "t", opp, r, ApprovalLevel.requires_approval)
        plan_blocked = bld.build("b", "t", opp,
                                 _make_readiness(ReadinessState.blocked, [], ["destination"], 0.0, "x"),
                                 ApprovalLevel.requires_approval)
        assert plan_blocked.confidence < plan_partial.confidence < plan_ready.confidence


class TestRecommendedNextAction:
    def test_ready_action_mentions_launch(self, bld):
        opp = _make_opp(ActionType.book, [])
        r = _make_readiness(ReadinessState.ready, [], [], 1.0)
        plan = bld.build("book", "t", opp, r, ApprovalLevel.requires_approval)
        assert "launch" in plan.recommended_next_action.lower() or "prepare" in plan.recommended_next_action.lower()

    def test_partially_ready_action_mentions_missing(self, bld):
        opp = _make_opp(ActionType.book, ["origin", "destination"])
        r = _make_readiness(ReadinessState.partially_ready, ["destination"], ["origin"], 0.5)
        plan = bld.build("book", "t", opp, r, ApprovalLevel.requires_approval)
        assert "origin" in plan.recommended_next_action

    def test_blocked_action_mentions_reason(self, bld):
        opp = _make_opp(ActionType.book, ["destination"])
        r = _make_readiness(ReadinessState.blocked, [], ["destination"], 0.0, "Missing destination")
        plan = bld.build("book", "t", opp, r, ApprovalLevel.requires_approval)
        assert "Missing destination" in plan.recommended_next_action


class TestApprovalLevel:
    def test_approval_level_stored(self, bld):
        opp = _make_opp(ActionType.purchase, [])
        r = _make_readiness(ReadinessState.ready, [], [], 1.0)
        plan = bld.build("buy", "t", opp, r, ApprovalLevel.high_risk)
        assert plan.approval_level == ApprovalLevel.high_risk
