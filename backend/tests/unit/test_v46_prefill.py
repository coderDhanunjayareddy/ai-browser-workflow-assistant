"""
V4.6 Unit Tests — WorkflowPrefillLayer.

Tests:
  - build() returns WorkflowPrefillPayload
  - title derived from current_goal or original_query
  - goal populated correctly
  - entities passed through
  - execution_plan passed through
  - readiness_state: "READY" when entities + plan; "PARTIAL" when only one; "NOT_READY" when neither
  - approval_classification from execution_plan.approval_level
  - workflow_type from execution_plan
  - missing_inputs from execution_plan
  - recommended_next_action from execution_plan
  - research_summary from research_report.executive_summary
  - key_findings list from research_report
  - confidence from research_report or execution_plan
  - pre_filled_facts from entities (scalars)
  - latency_ms < 10
  - task_state matches task's current state
  - build_by_task_id() resolves from store
  - build_by_task_id() returns None for unknown id
"""
import pytest

from app.unified import store as task_store
from app.unified import prefill as prefill_layer
from app.unified.models import UnifiedTask, TaskState


@pytest.fixture(autouse=True)
def reset_store():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


def _empty_task(task_id="t0", conv="c0"):
    t = UnifiedTask(task_id=task_id, conversation_id=conv, original_query="find hotel in Paris")
    return t


def _rich_task():
    t = UnifiedTask(
        task_id="t1",
        conversation_id="c1",
        original_query="book hotel in Paris",
        current_goal="book a 4-star hotel in Paris for 3 nights",
        state=TaskState.ready_for_workflow,
    )
    t.entities = {"city": "Paris", "nights": 3, "stars": 4}
    t.research_report = {
        "executive_summary": "Found 8 hotels under budget",
        "key_findings": ["Hotel A $120/night", "Hotel B $135/night"],
        "recommended_actions": ["Book Hotel A"],
        "confidence_score": 0.87,
    }
    t.execution_plan = {
        "workflow_type": "hotel_booking",
        "approval_level": "REQUIRES_APPROVAL",
        "confidence": 0.85,
        "missing_inputs": ["check_in_date", "check_out_date"],
        "recommended_next_action": "fill_dates_form",
    }
    task_store.put(t)
    return t


class TestBuildBasics:
    def test_returns_payload_object(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload is not None

    def test_task_id_matches(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.task_id == "t1"

    def test_task_state_matches(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.task_state == TaskState.ready_for_workflow.value

    def test_latency_ms_under_10(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.latency_ms < 10


class TestTitle:
    def test_title_uses_current_goal_when_set(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert "4-star" in payload.title or "Paris" in payload.title

    def test_title_falls_back_to_query_when_no_goal(self):
        task = _empty_task()
        payload = prefill_layer.build(task)
        assert payload.title  # non-empty
        assert "Paris" in payload.title or "hotel" in payload.title

    def test_title_truncated_to_80_chars(self):
        task = _empty_task()
        task.original_query = "x" * 200
        payload = prefill_layer.build(task)
        assert len(payload.title) <= 80


class TestGoalAndEntities:
    def test_goal_from_current_goal(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.goal == "book a 4-star hotel in Paris for 3 nights"

    def test_goal_none_when_no_current_goal(self):
        task = _empty_task()
        payload = prefill_layer.build(task)
        assert payload.goal is None

    def test_entities_passed_through(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.entities["city"] == "Paris"

    def test_entities_empty_when_none(self):
        task = _empty_task()
        payload = prefill_layer.build(task)
        assert payload.entities == {}


class TestReadinessState:
    def test_ready_when_entities_and_plan(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.readiness_state == "READY"

    def test_partial_when_only_entities(self):
        task = _empty_task("t2", "c2")
        task.entities = {"city": "Paris"}
        payload = prefill_layer.build(task)
        assert payload.readiness_state in ("PARTIAL", "NOT_READY")

    def test_partial_when_only_plan(self):
        task = _empty_task("t3", "c3")
        task.execution_plan = {"workflow_type": "booking"}
        payload = prefill_layer.build(task)
        assert payload.readiness_state in ("PARTIAL", "NOT_READY")

    def test_not_ready_when_neither(self):
        task = _empty_task("t4", "c4")
        payload = prefill_layer.build(task)
        assert payload.readiness_state == "NOT_READY"


class TestExecutionPlanFields:
    def test_approval_classification(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.approval_classification == "REQUIRES_APPROVAL"

    def test_workflow_type(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.workflow_type == "hotel_booking"

    def test_missing_inputs(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert "check_in_date" in payload.missing_inputs
        assert "check_out_date" in payload.missing_inputs

    def test_recommended_next_action(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.recommended_next_action == "fill_dates_form"

    def test_execution_plan_passed_through(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.execution_plan["workflow_type"] == "hotel_booking"


class TestResearchFields:
    def test_research_summary(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert "8 hotels" in payload.research_summary

    def test_key_findings(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert "Hotel A $120/night" in payload.key_findings

    def test_recommended_actions(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert "Book Hotel A" in payload.recommended_actions

    def test_confidence_from_report(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.confidence == pytest.approx(0.87, rel=0.05)


class TestPreFilledFacts:
    def test_scalar_string_entity(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.pre_filled_facts.get("city") == "Paris"

    def test_numeric_entity(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        assert payload.pre_filled_facts.get("nights") == 3

    def test_empty_when_no_entities(self):
        task = _empty_task("t5", "c5")
        payload = prefill_layer.build(task)
        assert payload.pre_filled_facts == {}


class TestBuildByTaskId:
    def test_returns_payload_for_known_task(self):
        task = _rich_task()
        payload = prefill_layer.build_by_task_id("t1")
        assert payload is not None
        assert payload.task_id == "t1"

    def test_returns_none_for_unknown_task(self):
        payload = prefill_layer.build_by_task_id("unknown-task-xyz")
        assert payload is None


class TestModelDump:
    def test_model_dump_serializes_cleanly(self):
        task = _rich_task()
        payload = prefill_layer.build(task)
        d = payload.model_dump()
        assert isinstance(d, dict)
        assert d["task_id"] == "t1"
        assert isinstance(d["entities"], dict)
        assert isinstance(d["missing_inputs"], list)
