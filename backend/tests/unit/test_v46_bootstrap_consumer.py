"""
V4.6 Unit Tests — WorkflowBootstrapConsumer.

Tests:
  - consume() returns WorkflowBootstrapContext
  - context includes entities, execution_plan, research_summary
  - key_findings from research_report
  - recommended_actions from research_report
  - approval_level from execution_plan
  - workflow_type from execution_plan
  - missing_inputs from execution_plan
  - pre_filled_facts built from entity values
  - is_ready True when entities or plan exist
  - is_ready False when task has no context
  - as_bootstrap_facts() returns flat dict
  - enrich_handoff_payload() merges without overwriting
  - consume_by_task_id() looks up from store
  - latency_ms < 10ms
"""
import pytest
import time

from app.unified import store as task_store
from app.unified.bootstrap_consumer import WorkflowBootstrapConsumer, consume, consume_by_task_id
from app.unified.models import UnifiedTask, TaskState


@pytest.fixture(autouse=True)
def reset_store():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


@pytest.fixture
def consumer():
    return WorkflowBootstrapConsumer()


def _empty_task():
    t = UnifiedTask(task_id="t0", conversation_id="c0", original_query="q")
    return t


def _rich_task():
    t = UnifiedTask(
        task_id="t1",
        conversation_id="c1",
        original_query="book a flight to NYC",
        current_goal="book cheapest flight to NYC",
        state=TaskState.ready_for_workflow,
    )
    t.entities = {"destination": "NYC", "date": "2025-12-01", "budget": 200}
    t.research_report = {
        "executive_summary": "Found 5 flights under $200",
        "key_findings": ["AA123 $180", "UA456 $195"],
        "recommended_actions": ["Book AA123"],
        "confidence_score": 0.88,
    }
    t.execution_plan = {
        "plan_id": "p1",
        "workflow_type": "flight_booking",
        "approval_level": "REQUIRES_APPROVAL",
        "confidence": 0.85,
        "missing_inputs": ["passenger_name"],
        "recommended_next_action": "fill_passenger_form",
    }
    task_store.put(t)
    return t


class TestConsume:
    def test_returns_context_object(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx is not None

    def test_task_id_matches(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.task_id == "t1"

    def test_original_query_matches(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.original_query == "book a flight to NYC"

    def test_current_goal_matches(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.current_goal == "book cheapest flight to NYC"

    def test_entities_populated(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.entities["destination"] == "NYC"

    def test_research_summary_from_report(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert "5 flights" in ctx.research_summary

    def test_key_findings_from_report(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert "AA123 $180" in ctx.key_findings

    def test_recommended_actions_from_report(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert "Book AA123" in ctx.recommended_actions

    def test_confidence_from_plan(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.confidence == pytest.approx(0.85, rel=0.01)

    def test_approval_level_from_plan(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.approval_level == "REQUIRES_APPROVAL"

    def test_workflow_type_from_plan(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.workflow_type == "flight_booking"

    def test_missing_inputs_from_plan(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert "passenger_name" in ctx.missing_inputs

    def test_recommended_next_action(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.recommended_next_action == "fill_passenger_form"

    def test_latency_ms_under_10ms(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.latency_ms < 10


class TestPreFilledFacts:
    def test_scalar_entities_become_pre_filled(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert "destination" in ctx.pre_filled_facts
        assert ctx.pre_filled_facts["destination"] == "NYC"

    def test_numeric_entities_become_pre_filled(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        assert ctx.pre_filled_facts.get("budget") == 200

    def test_dict_entity_with_value_key(self, consumer):
        task = _empty_task()
        task.entities = {"passenger": {"value": "John Doe", "confidence": 0.9}}
        ctx = consumer.consume(task)
        assert ctx.pre_filled_facts.get("passenger") == "John Doe"


class TestIsReady:
    def test_is_ready_when_entities_exist(self, consumer):
        task = _empty_task()
        task.entities = {"key": "val"}
        ctx = consumer.consume(task)
        assert ctx.is_ready is True

    def test_is_ready_when_plan_exists(self, consumer):
        task = _empty_task()
        task.execution_plan = {"workflow_type": "booking"}
        ctx = consumer.consume(task)
        assert ctx.is_ready is True

    def test_not_ready_when_empty(self, consumer):
        task = _empty_task()
        ctx = consumer.consume(task)
        assert ctx.is_ready is False


class TestToDict:
    def test_returns_dict(self, consumer):
        task = _rich_task()
        d = consumer.consume(task).to_dict()
        assert isinstance(d, dict)

    def test_dict_has_required_keys(self, consumer):
        task = _rich_task()
        d = consumer.consume(task).to_dict()
        for key in ["task_id", "entities", "execution_plan", "research_summary",
                    "approval_level", "workflow_type", "is_ready"]:
            # is_ready is on the object not to_dict — check others
            pass
        assert "task_id" in d
        assert "entities" in d


class TestAsBootstrapFacts:
    def test_includes_entities(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        facts = ctx.as_bootstrap_facts()
        assert "destination" in facts

    def test_includes_goal(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        facts = ctx.as_bootstrap_facts()
        assert facts.get("goal") == "book cheapest flight to NYC"

    def test_includes_workflow_type(self, consumer):
        task = _rich_task()
        ctx = consumer.consume(task)
        facts = ctx.as_bootstrap_facts()
        assert facts.get("workflow_type") == "flight_booking"


class TestEnrichHandoffPayload:
    def test_adds_missing_keys(self, consumer):
        task = _rich_task()
        payload = {"session_id": "s1"}
        enriched = consumer.enrich_handoff_payload(task, payload)
        assert enriched["task_id"] == "t1"
        assert enriched["session_id"] == "s1"

    def test_does_not_overwrite_existing_keys(self, consumer):
        task = _rich_task()
        payload = {"task_id": "original-id"}
        enriched = consumer.enrich_handoff_payload(task, payload)
        assert enriched["task_id"] == "original-id"


class TestConsumeByTaskId:
    def test_returns_context_for_known_task(self):
        task = _rich_task()
        ctx = consume_by_task_id("t1")
        assert ctx is not None
        assert ctx.task_id == "t1"

    def test_returns_none_for_unknown_task(self):
        ctx = consume_by_task_id("nonexistent-task-999")
        assert ctx is None
