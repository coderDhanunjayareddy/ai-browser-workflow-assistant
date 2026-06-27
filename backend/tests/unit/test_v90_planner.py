"""V9.0 Execution Planning Layer — Unit tests: planner.py."""
import time
import pytest
from app.execution_planning import planner
from app.execution_planning.planner import PlannerInputError, ExecutionPlanner
from app.execution_planning.models import (
    ActionType, ExecutionMode, PlanStatus, ValidationStrategy,
)
from app.authorization.models import make_authorization


def _auth(risk="HIGH", mission="m-1", task="t-1", authorized=True):
    return make_authorization("ctr-1", authorized, "ok", risk, time.time() + 3600,
                              mission_id=mission, task_id=task)


class _FakeNode:
    def __init__(self, node_id, description, prerequisites=None):
        self.node_id = node_id
        self.description = description
        self.prerequisites = prerequisites or []


class _FakeGraph:
    def __init__(self, nodes):
        self.nodes = nodes


class _FakeRuntimeCtx:
    def __init__(self, last_url):
        self.last_url = last_url


class _FakeMission:
    def __init__(self, objective="research X", metadata=None):
        self.objective = objective
        self.metadata = metadata or {}


class TestInputContract:
    def test_rejects_non_authorization(self):
        with pytest.raises(PlannerInputError):
            planner.create_plan({"authorization_id": "fake"})

    def test_rejects_string(self):
        with pytest.raises(PlannerInputError):
            planner.create_plan("auth-1")

    def test_rejects_none(self):
        with pytest.raises(PlannerInputError):
            planner.create_plan(None)

    def test_accepts_authorization(self):
        p = planner.create_plan(_auth())
        assert p is not None


class TestCanonicalPlan:
    def test_three_steps(self):
        p = planner.create_plan(_auth())
        assert p.estimated_steps == 3

    def test_step_order(self):
        p = planner.create_plan(_auth())
        actions = [s.action_type for s in p.steps]
        assert actions == [ActionType.navigate, ActionType.extract, ActionType.validate]

    def test_status_draft(self):
        assert planner.create_plan(_auth()).status == PlanStatus.draft

    def test_authorization_id_propagated(self):
        a = _auth()
        p = planner.create_plan(a)
        assert p.authorization_id == a.authorization_id

    def test_mission_task_propagated(self):
        p = planner.create_plan(_auth(mission="m-X", task="t-Y"))
        assert p.mission_id == "m-X"
        assert p.task_id == "t-Y"

    def test_navigate_has_url_param(self):
        p = planner.create_plan(_auth())
        nav = p.steps[0]
        assert "url" in nav.parameters

    def test_steps_have_approval_scope(self):
        p = planner.create_plan(_auth())
        assert all(s.approval_scope for s in p.steps)

    def test_metadata_source_canonical(self):
        p = planner.create_plan(_auth())
        assert p.metadata["source"] == "canonical"


class TestEstimates:
    def test_duration_is_sum(self):
        # navigate 800 + extract 400 + validate 250 = 1450
        p = planner.create_plan(_auth())
        assert p.estimated_duration_ms == 1450

    def test_rollback_supported_true(self):
        # only navigate is mutating and has navigate_back rollback
        p = planner.create_plan(_auth())
        assert p.rollback_supported is True

    def test_confidence_range(self):
        p = planner.create_plan(_auth())
        assert 0.0 <= p.confidence <= 1.0

    def test_confidence_higher_with_runtime(self):
        p_no = planner.create_plan(_auth())
        p_rt = planner.create_plan(_auth(), runtime_context=_FakeRuntimeCtx("http://a"))
        assert p_rt.confidence > p_no.confidence

    def test_deterministic_structure(self):
        a = _auth()
        p1 = planner.create_plan(a, now=100.0)
        p2 = planner.create_plan(a, now=100.0)
        assert [s.action_type for s in p1.steps] == [s.action_type for s in p2.steps]
        assert p1.estimated_duration_ms == p2.estimated_duration_ms
        assert p1.confidence == p2.confidence
        assert p1.execution_mode == p2.execution_mode


class TestExecutionMode:
    def test_critical_dry_run(self):
        p = planner.create_plan(_auth(risk="CRITICAL"))
        assert p.execution_mode == ExecutionMode.dry_run

    def test_mutating_atomic(self):
        # canonical plan has navigate (mutating) + rollback supported → ATOMIC
        p = planner.create_plan(_auth(risk="HIGH"))
        assert p.execution_mode == ExecutionMode.atomic


class TestTargetUrlResolution:
    def test_uses_runtime_url(self):
        p = planner.create_plan(_auth(), runtime_context=_FakeRuntimeCtx("http://live"))
        assert p.steps[0].parameters["url"] == "http://live"

    def test_uses_mission_target_url(self):
        m = _FakeMission(metadata={"target_url": "http://mission"})
        p = planner.create_plan(_auth(), mission=m)
        assert p.steps[0].parameters["url"] == "http://mission"

    def test_default_about_blank(self):
        p = planner.create_plan(_auth())
        assert p.steps[0].parameters["url"] == "about:blank"

    def test_objective_in_metadata(self):
        m = _FakeMission(objective="compare laptops")
        p = planner.create_plan(_auth(), mission=m)
        assert p.metadata["objective"] == "compare laptops"


class TestWorkflowGraph:
    def test_steps_from_graph(self):
        graph = _FakeGraph([
            _FakeNode("n1", "Navigate to homepage"),
            _FakeNode("n2", "Click the search button"),
            _FakeNode("n3", "Extract the results"),
        ])
        p = planner.create_plan(_auth(), workflow_graph=graph)
        assert p.estimated_steps == 3
        assert p.steps[0].action_type == ActionType.navigate
        assert p.steps[1].action_type == ActionType.click
        assert p.steps[2].action_type == ActionType.extract

    def test_graph_source_metadata(self):
        graph = _FakeGraph([_FakeNode("n1", "Read the page")])
        p = planner.create_plan(_auth(), workflow_graph=graph)
        assert p.metadata["source"] == "workflow_graph"

    def test_node_id_in_params(self):
        graph = _FakeGraph([_FakeNode("node-42", "Type the query")])
        p = planner.create_plan(_auth(), workflow_graph=graph)
        assert p.steps[0].parameters["node_id"] == "node-42"

    def test_unknown_description_defaults_read(self):
        graph = _FakeGraph([_FakeNode("n1", "something undefined")])
        p = planner.create_plan(_auth(), workflow_graph=graph)
        assert p.steps[0].action_type == ActionType.read

    def test_empty_graph_falls_back_to_canonical(self):
        p = planner.create_plan(_auth(), workflow_graph=_FakeGraph([]))
        assert p.metadata["source"] == "canonical"

    def test_prerequisites_preserved(self):
        graph = _FakeGraph([_FakeNode("n2", "Click submit", prerequisites=["n1"])])
        p = planner.create_plan(_auth(), workflow_graph=graph)
        assert p.steps[0].parameters["prerequisites"] == ["n1"]


class TestActionInference:
    @pytest.mark.parametrize("desc,expected", [
        ("Navigate to site", ActionType.navigate),
        ("open the page", ActionType.navigate),
        ("Click the button", ActionType.click),
        ("submit the form", ActionType.click),
        ("Type the search query", ActionType.input),
        ("fill in the field", ActionType.input),
        ("Extract all data", ActionType.extract),
        ("scrape results", ActionType.extract),
        ("Scroll down", ActionType.scroll),
        ("wait for load", ActionType.wait),
        ("Verify the result", ActionType.validate),
        ("check the output", ActionType.validate),
        ("random text", ActionType.read),
    ])
    def test_infer(self, desc, expected):
        eng = ExecutionPlanner()
        action, _ = eng._infer_action(desc)
        assert action == expected
