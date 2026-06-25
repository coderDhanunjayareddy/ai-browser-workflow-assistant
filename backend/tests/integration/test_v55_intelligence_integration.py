"""
V5.5 Integration tests — Mission Intelligence Layer (32 tests).

Tests the full stack: API routes → engine → components → in-memory stores.
No DB, no LLM, no external APIs.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mission import store as mission_store, lifecycle as mission_lifecycle
from app.unified import store as task_store
from app.mission.intelligence import (
    registry as intel_registry,
    analytics as intel_analytics,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_all():
    mission_store._reset_for_testing()
    task_store._reset_for_testing()
    intel_registry._reset_for_testing()
    intel_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    task_store._reset_for_testing()
    intel_registry._reset_for_testing()
    intel_analytics._reset_for_testing()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_mission(title="Buy MacBook", objective=""):
    resp = client.post("/mission/", json={"title": title, "objective": objective})
    assert resp.status_code == 200
    return resp.json()


def _create_task(query="research laptops"):
    from app.unified.models import UnifiedTask, TaskState
    import uuid
    t = UnifiedTask(
        task_id=str(uuid.uuid4())[:8],
        conversation_id="c1",
        original_query=query,
        state=TaskState.completed,
    )
    task_store.put(t)
    return t


def _give_research(task):
    task.research_report = {
        "topic": "laptops",
        "summary": "Laptop research complete.",
        "sources": [],
        "key_findings": [],
        "confidence": 0.90,
    }


def _give_plan(task):
    task.execution_plan = {"workflow_type": "purchase_workflow", "plan_id": "p1"}


def _attach(mission_id, task_id):
    resp = client.post(f"/mission/{mission_id}/tasks/{task_id}")
    assert resp.status_code == 200
    return resp.json()


# ── GET /mission/{id}/intelligence ────────────────────────────────────────────

class TestGetIntelligenceEndpoint:
    def test_404_for_missing_mission(self):
        resp = client.get("/mission/nonexistent/intelligence")
        assert resp.status_code == 404

    def test_returns_200_for_existing_mission(self):
        m = _create_mission()
        resp = client.get(f"/mission/{m['mission_id']}/intelligence")
        assert resp.status_code == 200

    def test_response_has_all_fields(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/intelligence").json()
        required = [
            "mission_id", "readiness_score", "confidence",
            "recommended_action", "blockers", "missing_information",
            "reasoning", "next_action", "advisory_state",
            "generated_at", "latency_ms",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_readiness_score_is_numeric(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/intelligence").json()
        assert isinstance(data["readiness_score"], float)
        assert 0.0 <= data["readiness_score"] <= 1.0

    def test_empty_mission_has_no_tasks_blocker(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/intelligence").json()
        codes = [b["code"] for b in data["blockers"]]
        assert "NO_TASKS" in codes

    def test_force_refresh_param_accepted(self):
        m = _create_mission()
        resp = client.get(f"/mission/{m['mission_id']}/intelligence?force_refresh=true")
        assert resp.status_code == 200

    def test_with_completed_task_readiness_increases(self):
        m = _create_mission()
        t = _create_task()
        _give_research(t)
        _give_plan(t)
        _attach(m["mission_id"], t.task_id)

        r1_score = client.get(f"/mission/{m['mission_id']}/intelligence").json()["readiness_score"]

        # Create another mission with no tasks
        m2 = _create_mission("Another Mission")
        r2_score = client.get(f"/mission/{m2['mission_id']}/intelligence").json()["readiness_score"]

        assert r1_score > r2_score


# ── GET /mission/{id}/readiness ───────────────────────────────────────────────

class TestReadinessEndpoint:
    def test_404_for_missing_mission(self):
        resp = client.get("/mission/nonexistent/readiness")
        assert resp.status_code == 404

    def test_returns_readiness_score(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/readiness").json()
        assert "readiness_score" in data
        assert "advisory_state" in data
        assert "blockers" in data

    def test_readiness_score_is_in_range(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/readiness").json()
        assert 0.0 <= data["readiness_score"] <= 1.0

    def test_advisory_state_is_valid_string(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/readiness").json()
        valid_states = {"ACTIVE", "PAUSED", "BLOCKED", "READY", "COMPLETED"}
        assert data["advisory_state"] in valid_states


# ── GET /mission/{id}/blockers ────────────────────────────────────────────────

class TestBlockersEndpoint:
    def test_404_for_missing_mission(self):
        resp = client.get("/mission/nonexistent/blockers")
        assert resp.status_code == 404

    def test_returns_blockers_list(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/blockers").json()
        assert "blockers" in data
        assert "blocker_count" in data

    def test_empty_mission_has_no_tasks_blocker(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/blockers").json()
        codes = [b["code"] for b in data["blockers"]]
        assert "NO_TASKS" in codes

    def test_blocker_count_matches_list_length(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/blockers").json()
        assert data["blocker_count"] == len(data["blockers"])

    def test_blocker_has_severity_field(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/blockers").json()
        for b in data["blockers"]:
            assert "severity" in b
            assert b["severity"] in {"CRITICAL", "WARNING", "INFO"}


# ── GET /mission/{id}/next-action ─────────────────────────────────────────────

class TestNextActionEndpoint:
    def test_404_for_missing_mission(self):
        resp = client.get("/mission/nonexistent/next-action")
        assert resp.status_code == 404

    def test_returns_next_action(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/next-action").json()
        assert "next_action" in data
        na = data["next_action"]
        assert "action" in na
        assert "reasoning" in na
        assert "priority" in na

    def test_priority_is_int_1_to_3(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/next-action").json()
        assert data["next_action"]["priority"] in {1, 2, 3}


# ── GET /mission/{id}/workflow-recommendation ─────────────────────────────────

class TestWorkflowRecommendationEndpoint:
    def test_404_for_missing_mission(self):
        resp = client.get("/mission/nonexistent/workflow-recommendation")
        assert resp.status_code == 404

    def test_returns_workflow_recommendation_field(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/workflow-recommendation").json()
        assert "workflow_recommendation" in data
        assert "readiness_score" in data

    def test_purchase_mission_returns_purchase_workflow(self):
        m = _create_mission("Order laptop online")
        t = _create_task("order laptop")
        _give_research(t)
        _give_plan(t)
        _attach(m["mission_id"], t.task_id)

        data = client.get(f"/mission/{m['mission_id']}/workflow-recommendation").json()
        if data["workflow_recommendation"] is not None:
            assert data["workflow_recommendation"]["workflow_type"] == "purchase_workflow"


# ── GET /mission/intelligence/analytics ───────────────────────────────────────

class TestIntelligenceAnalyticsEndpoint:
    def test_analytics_endpoint_returns_200(self):
        resp = client.get("/mission/intelligence/analytics")
        assert resp.status_code == 200

    def test_analytics_has_all_required_fields(self):
        data = client.get("/mission/intelligence/analytics").json()
        required = [
            "intelligence_runs", "cache_hits", "cache_misses",
            "cache_hit_rate", "readiness_evaluations", "avg_readiness_score",
            "blocker_detections", "total_blockers_found",
            "workflow_recommendations", "next_action_generations", "avg_latency_ms",
        ]
        for field in required:
            assert field in data, f"Missing: {field}"

    def test_run_increments_intelligence_runs(self):
        m = _create_mission()
        client.get(f"/mission/{m['mission_id']}/intelligence")
        data = client.get("/mission/intelligence/analytics").json()
        assert data["intelligence_runs"] >= 1


# ── Inspector includes intelligence ───────────────────────────────────────────

class TestInspectorIntelligence:
    def test_inspect_includes_intelligence_section(self):
        m = _create_mission()
        data = client.get(f"/mission/{m['mission_id']}/inspect").json()
        assert "intelligence" in data
        if data["intelligence"] is not None:
            assert "readiness_score" in data["intelligence"]
            assert "advisory_state" in data["intelligence"]
