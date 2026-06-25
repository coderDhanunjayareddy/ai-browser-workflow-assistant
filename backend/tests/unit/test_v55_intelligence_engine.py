"""
V5.5 Unit tests — MissionIntelligenceEngine (22 tests).

Tests for the end-to-end engine.run() orchestration.
Uses real in-memory stores (no DB, no mocking).
"""
import pytest

from app.mission.intelligence import engine as intel_engine, registry as intel_registry
from app.mission.intelligence import analytics as intel_analytics
from app.mission.intelligence.models import MissionAdvisoryState


@pytest.fixture(autouse=True)
def reset_state():
    """Reset caches and analytics between tests."""
    from app.mission import store as mission_store
    from app.unified import store as task_store
    mission_store._reset_for_testing()
    task_store._reset_for_testing()
    intel_registry._reset_for_testing()
    intel_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    task_store._reset_for_testing()
    intel_registry._reset_for_testing()
    intel_analytics._reset_for_testing()


def _create_mission(title="Buy MacBook", objective=""):
    from app.mission.lifecycle import create_mission_obj
    return create_mission_obj(title=title, objective=objective)


def _create_task(query="research laptops", state="COMPLETED"):
    from app.unified.models import UnifiedTask, TaskState
    from app.unified import store as task_store
    import uuid
    task = UnifiedTask(
        task_id=str(uuid.uuid4())[:8],
        conversation_id="c1",
        original_query=query,
        state=TaskState(state),
    )
    task_store.put(task)
    return task


def _set_task_state(task, state_str):
    from app.unified.models import TaskState
    task.state = TaskState(state_str)


def _give_task_research(task):
    task.research_report = {
        "topic": "laptops",
        "summary": "Laptop research complete.",
        "sources": [],
        "key_findings": [],
        "confidence": 0.90,
    }


def _give_task_plan(task):
    task.execution_plan = {"workflow_type": "purchase_workflow", "plan_id": "p1"}


def _attach(mission, task):
    from app.mission.lifecycle import attach_task
    attach_task(mission.mission_id, task.task_id)


class TestEngineOnNonexistentMission:
    def test_returns_none_for_missing_mission(self):
        result = intel_engine.run("nonexistent_id")
        assert result is None


class TestEngineOnEmptyMission:
    def test_empty_mission_produces_report(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        assert report is not None
        assert report.mission_id == m.mission_id

    def test_empty_mission_low_readiness(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        assert report.readiness_score == 0.0

    def test_empty_mission_blocked_by_no_tasks(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        codes = [b.code for b in report.blockers]
        assert "NO_TASKS" in codes

    def test_empty_mission_advisory_state_is_active(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        assert report.advisory_state == MissionAdvisoryState.active


class TestEngineWithTasks:
    def test_mission_with_completed_research_task_has_higher_score(self):
        m = _create_mission()
        t = _create_task()
        _give_task_research(t)
        _attach(m, t)
        report = intel_engine.run(m.mission_id)
        assert report.readiness_score > 0.0

    def test_mission_with_plan_has_high_readiness(self):
        m = _create_mission("Buy MacBook")
        t = _create_task("research laptops")
        _give_task_research(t)
        _give_task_plan(t)
        _attach(m, t)
        report = intel_engine.run(m.mission_id)
        assert report.readiness_score >= 0.60

    def test_failed_task_triggers_blocked_state(self):
        m = _create_mission()
        t = _create_task()
        _set_task_state(t, "FAILED")
        _give_task_research(t)
        _attach(m, t)
        report = intel_engine.run(m.mission_id)
        assert report.advisory_state == MissionAdvisoryState.blocked

    def test_report_has_next_action(self):
        m = _create_mission()
        t = _create_task()
        _give_task_research(t)
        _attach(m, t)
        report = intel_engine.run(m.mission_id)
        assert report.next_action is not None
        assert len(report.next_action.action) > 0

    def test_purchase_mission_gets_workflow_recommendation(self):
        m = _create_mission("Order laptop online")
        t = _create_task("order laptop")
        _give_task_research(t)
        _give_task_plan(t)
        _attach(m, t)
        report = intel_engine.run(m.mission_id)
        assert report.workflow_recommendation is not None
        assert report.suggested_workflow == "purchase_workflow"


class TestCaching:
    def test_second_call_returns_cached(self):
        m = _create_mission()
        t = _create_task()
        _give_task_research(t)
        _attach(m, t)
        r1 = intel_engine.run(m.mission_id)
        r2 = intel_engine.run(m.mission_id)
        assert r1 is r2  # same object from cache

    def test_force_refresh_recomputes(self):
        m = _create_mission()
        t = _create_task()
        _give_task_research(t)
        _attach(m, t)
        r1 = intel_engine.run(m.mission_id)
        r2 = intel_engine.run(m.mission_id, force_refresh=True)
        # Objects may differ (new report generated) but data should be equivalent
        assert r2.readiness_score == r1.readiness_score

    def test_cache_invalidation_triggers_recompute(self):
        m = _create_mission()
        t = _create_task()
        _give_task_research(t)
        _attach(m, t)
        r1 = intel_engine.run(m.mission_id)
        intel_registry.invalidate(m.mission_id)
        r2 = intel_engine.run(m.mission_id)
        assert r1 is not r2  # fresh object after invalidation


class TestAnalytics:
    def test_intelligence_run_increments_counter(self):
        m = _create_mission()
        intel_engine.run(m.mission_id)
        data = intel_analytics.get_analytics()
        assert data["intelligence_runs"] >= 1

    def test_cache_hit_increments_hit_counter(self):
        m = _create_mission()
        intel_engine.run(m.mission_id)  # first: miss + run
        intel_engine.run(m.mission_id)  # second: hit
        data = intel_analytics.get_analytics()
        assert data["cache_hits"] >= 1

    def test_readiness_evaluation_incremented(self):
        m = _create_mission()
        intel_engine.run(m.mission_id)
        data = intel_analytics.get_analytics()
        assert data["readiness_evaluations"] >= 1


class TestReportFields:
    def test_report_has_all_required_fields(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        assert hasattr(report, "mission_id")
        assert hasattr(report, "readiness_score")
        assert hasattr(report, "confidence")
        assert hasattr(report, "recommended_action")
        assert hasattr(report, "blockers")
        assert hasattr(report, "missing_information")
        assert hasattr(report, "reasoning")
        assert hasattr(report, "next_action")
        assert hasattr(report, "advisory_state")
        assert hasattr(report, "generated_at")
        assert hasattr(report, "latency_ms")

    def test_readiness_score_in_range(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        assert 0.0 <= report.readiness_score <= 1.0

    def test_confidence_in_range(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        assert 0.0 <= report.confidence <= 1.0

    def test_latency_ms_is_non_negative(self):
        m = _create_mission()
        report = intel_engine.run(m.mission_id)
        assert report.latency_ms >= 0
