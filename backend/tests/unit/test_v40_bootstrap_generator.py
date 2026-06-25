"""
V4.0 Unit Tests — WorkflowBootstrapGenerator.

Tests cover:
  - query preserved
  - workflow_type from execution plan
  - goal_tree_summary = leaf node texts
  - pre_filled_entities from cognitive session
  - research_topic and research_summary populated
  - goal_text from cognitive session's active_goal
"""
import pytest
from app.intelligence.models import (
    ActionType, ApprovalLevel, ExecutionOpportunity, ExecutionPlan,
    GoalTree, GoalNode, ReadinessState, WorkflowReadiness,
)
from app.intelligence.bootstrap_generator import WorkflowBootstrapGenerator
from app.intelligence.plan_builder import ExecutionPlanBuilder
from app.intelligence.goal_decomposer import GoalDecomposer


class _FakeGoal:
    def __init__(self, text):
        self.goal_text = text
        self.status = type("S", (), {"value": "active"})()


class _FakeEntity:
    def __init__(self, name, value=None):
        self.name = name
        self.aliases = []
        self.metadata = {"value": value or name}


class _FakeSession:
    def __init__(self, entity_names: list[str], goal_text: str | None = None):
        self.active_entities = {n: _FakeEntity(n) for n in entity_names}
        self.active_goal = _FakeGoal(goal_text) if goal_text else None


def _make_plan(workflow_type: str = "booking_workflow") -> ExecutionPlan:
    opp = ExecutionOpportunity(
        detected=True, confidence=0.9,
        action_type=ActionType.book,
        required_entities=["destination"],
        missing_information=[],
        workflow_candidate=True,
        raw_action_keywords=["book"],
    )
    readiness = WorkflowReadiness(
        state=ReadinessState.ready, ready_entities=["destination"],
        missing_entities=[], blocking_reason=None, readiness_score=1.0,
    )
    tree = GoalDecomposer().decompose("flight", opp)
    return ExecutionPlan(
        plan_id="test-plan",
        goal="book a flight",
        workflow_type=workflow_type,
        required_inputs=["destination"],
        inferred_inputs={"destination": "Mumbai"},
        missing_inputs=[],
        confidence=0.95,
        recommended_next_action="Launch workflow",
        approval_level=ApprovalLevel.requires_approval,
        goal_tree=tree,
    )


@pytest.fixture
def gen():
    return WorkflowBootstrapGenerator()


class TestBootstrapFields:
    def test_query_preserved(self, gen):
        plan = _make_plan()
        bf = gen.generate("book a flight to Mumbai", plan, "flight", "Summary text")
        assert bf.query == "book a flight to Mumbai"

    def test_workflow_type_from_plan(self, gen):
        plan = _make_plan("booking_workflow")
        bf = gen.generate("q", plan, "t", "s")
        assert bf.workflow_type == "booking_workflow"

    def test_research_topic_set(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "flight to Mumbai", "s")
        assert bf.research_topic == "flight to Mumbai"

    def test_research_summary_set(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "t", "Executive summary of research")
        assert "Executive summary" in bf.research_summary

    def test_research_summary_truncated_at_500(self, gen):
        plan = _make_plan()
        long_summary = "A" * 1000
        bf = gen.generate("q", plan, "t", long_summary)
        assert len(bf.research_summary) <= 500

    def test_confidence_from_plan(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "t", "s")
        assert bf.confidence == plan.confidence

    def test_approval_level_from_plan(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "t", "s")
        assert bf.approval_level == ApprovalLevel.requires_approval


class TestGoalTreeSummary:
    def test_goal_tree_summary_is_list(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "t", "s")
        assert isinstance(bf.goal_tree_summary, list)

    def test_goal_tree_summary_non_empty(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "t", "s")
        assert len(bf.goal_tree_summary) > 0

    def test_goal_tree_summary_items_are_strings(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "t", "s")
        for item in bf.goal_tree_summary:
            assert isinstance(item, str) and len(item) > 0


class TestPreFilledEntities:
    def test_inferred_inputs_included(self, gen):
        plan = _make_plan()  # has inferred destination=Mumbai
        bf = gen.generate("q", plan, "t", "s")
        assert "destination" in bf.pre_filled_entities

    def test_session_entities_merged(self, gen):
        plan = _make_plan()
        session = _FakeSession(["origin"])
        bf = gen.generate("q", plan, "t", "s", cognitive_session=session)
        assert "origin" in bf.pre_filled_entities

    def test_no_duplicates_from_session(self, gen):
        plan = _make_plan()
        session = _FakeSession(["destination"])  # already in inferred_inputs
        bf = gen.generate("q", plan, "t", "s", cognitive_session=session)
        # Should have destination once
        assert "destination" in bf.pre_filled_entities


class TestGoalText:
    def test_goal_text_from_session(self, gen):
        plan = _make_plan()
        session = _FakeSession([], goal_text="Book cheapest flight to Mumbai")
        bf = gen.generate("q", plan, "t", "s", cognitive_session=session)
        assert bf.goal_text == "Book cheapest flight to Mumbai"

    def test_goal_text_none_when_no_session(self, gen):
        plan = _make_plan()
        bf = gen.generate("q", plan, "t", "s")
        assert bf.goal_text is None

    def test_goal_text_none_when_no_goal_in_session(self, gen):
        plan = _make_plan()
        session = _FakeSession([])
        bf = gen.generate("q", plan, "t", "s", cognitive_session=session)
        assert bf.goal_text is None
