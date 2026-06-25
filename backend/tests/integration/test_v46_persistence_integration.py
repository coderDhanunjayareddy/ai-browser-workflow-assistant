"""
V4.6 Integration Tests — Persistence + Unified API Endpoints.

Tests all 5 new V4.6 REST endpoints using FastAPI TestClient.
All tests use the SQLite in-memory DB injected by conftest.py.

Endpoints tested:
  GET /unified/tasks/{id}/restore  → TaskRestorationSchema
  GET /unified/tasks/{id}/snapshots → list[TaskSnapshotSchema]
  GET /unified/tasks/{id}/bootstrap → WorkflowBootstrapSchema
  GET /unified/tasks/{id}/prefill   → WorkflowPrefillSchema
  GET /unified/tasks/{id}/inspect   → UnifiedTaskSchema
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.unified import store as task_store
from app.unified import persistence as task_persistence
from app.unified import snapshot as snap_system
from app.unified.models import UnifiedTask, TaskState


client = TestClient(app)

TASK_ID = "integ-t1"
CONV_ID = "integ-conv-1"


@pytest.fixture(autouse=True)
def reset_state():
    task_store._reset_for_testing()
    yield
    task_store._reset_for_testing()


def _seed_task(
    task_id=TASK_ID,
    conv_id=CONV_ID,
    state=TaskState.ready_for_workflow,
    with_entities=True,
    with_plan=True,
    with_report=True,
):
    """Create, persist, and register a task in memory + DB."""
    t = UnifiedTask(
        task_id=task_id,
        conversation_id=conv_id,
        original_query="book a flight to NYC",
        current_goal="book cheapest flight to NYC",
        state=state,
    )
    if with_entities:
        t.entities = {"destination": "NYC", "date": "2025-12-01"}
    if with_report:
        t.research_report = {
            "executive_summary": "Found 5 flights under $200",
            "key_findings": ["AA123 $180"],
            "recommended_actions": ["Book AA123"],
            "confidence_score": 0.88,
        }
    if with_plan:
        t.execution_plan = {
            "workflow_type": "flight_booking",
            "approval_level": "REQUIRES_APPROVAL",
            "confidence": 0.85,
            "missing_inputs": ["passenger_name"],
            "recommended_next_action": "fill_passenger_form",
        }
    task_store.put(t)
    task_persistence.save(t)
    return t


# ── GET /unified/tasks/{id}/restore ──────────────────────────────────────────

class TestRestoreEndpoint:
    def test_200_for_task_in_memory(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/restore")
        assert r.status_code == 200

    def test_restored_from_memory(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/restore")
        assert r.json()["restored_from"] == "memory"

    def test_task_id_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/restore")
        assert r.json()["task_id"] == TASK_ID

    def test_task_state_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/restore")
        assert r.json()["task_state"] == TaskState.ready_for_workflow.value

    def test_original_query_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/restore")
        assert r.json()["original_query"] == "book a flight to NYC"

    def test_current_goal_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/restore")
        assert r.json()["current_goal"] == "book cheapest flight to NYC"

    def test_latency_ms_present(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/restore")
        assert r.json()["latency_ms"] >= 0

    def test_404_for_unknown_task(self):
        r = client.get("/unified/tasks/does-not-exist-xyz/restore")
        assert r.status_code == 404

    def test_slow_path_restores_from_db(self):
        """Save to DB but not memory, then restore should load from DB."""
        t = UnifiedTask(task_id="db-only", conversation_id="c-db-only")
        task_persistence.save(t)
        # Don't put in memory store
        r = client.get("/unified/tasks/db-only/restore")
        assert r.status_code == 200
        assert r.json()["restored_from"] == "database"


# ── GET /unified/tasks/{id}/snapshots ────────────────────────────────────────

class TestSnapshotsEndpoint:
    def test_200_with_empty_list(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/snapshots")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_snapshot_after_create(self):
        task = _seed_task()
        snap_system.create(task, "research_complete")
        r = client.get(f"/unified/tasks/{TASK_ID}/snapshots")
        assert r.status_code == 200
        snaps = r.json()
        assert len(snaps) == 1

    def test_snapshot_has_trigger(self):
        task = _seed_task()
        snap_system.create(task, "workflow_prepared")
        r = client.get(f"/unified/tasks/{TASK_ID}/snapshots")
        assert r.json()[0]["trigger"] == "workflow_prepared"

    def test_snapshot_has_task_state(self):
        task = _seed_task()
        snap_system.create(task, "research_complete")
        r = client.get(f"/unified/tasks/{TASK_ID}/snapshots")
        assert "task_state" in r.json()[0]

    def test_snapshot_has_snapshot_id(self):
        task = _seed_task()
        snap_system.create(task, "research_complete")
        r = client.get(f"/unified/tasks/{TASK_ID}/snapshots")
        assert "snapshot_id" in r.json()[0]

    def test_multiple_snapshots_returned(self):
        task = _seed_task()
        snap_system.create(task, "research_complete")
        snap_system.create(task, "workflow_prepared")
        r = client.get(f"/unified/tasks/{TASK_ID}/snapshots")
        assert len(r.json()) == 2

    def test_404_for_unknown_task(self):
        r = client.get("/unified/tasks/no-such-task/snapshots")
        assert r.status_code == 404


# ── GET /unified/tasks/{id}/bootstrap ────────────────────────────────────────

class TestBootstrapEndpoint:
    def test_200_for_seeded_task(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/bootstrap")
        assert r.status_code == 200

    def test_entities_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/bootstrap")
        assert r.json()["entities"]["destination"] == "NYC"

    def test_workflow_type_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/bootstrap")
        assert r.json()["workflow_type"] == "flight_booking"

    def test_approval_level_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/bootstrap")
        assert r.json()["approval_level"] == "REQUIRES_APPROVAL"

    def test_key_findings_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/bootstrap")
        assert "AA123 $180" in r.json()["key_findings"]

    def test_is_ready_true_when_context_exists(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/bootstrap")
        assert r.json()["is_ready"] is True

    def test_is_ready_false_when_no_context(self):
        t = UnifiedTask(task_id="empty-t", conversation_id="empty-c")
        task_store.put(t)
        r = client.get("/unified/tasks/empty-t/bootstrap")
        assert r.json()["is_ready"] is False

    def test_latency_ms_under_10(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/bootstrap")
        assert r.json()["latency_ms"] < 10

    def test_404_for_unknown_task(self):
        r = client.get("/unified/tasks/bootstrap-404/bootstrap")
        assert r.status_code == 404

    def test_restores_from_db_when_not_in_memory(self):
        """Bootstrap should restore the task from DB if not in memory."""
        t = UnifiedTask(task_id="boot-db", conversation_id="boot-conv")
        t.entities = {"city": "London"}
        task_persistence.save(t)
        r = client.get("/unified/tasks/boot-db/bootstrap")
        assert r.status_code == 200
        assert r.json()["entities"]["city"] == "London"


# ── GET /unified/tasks/{id}/prefill ──────────────────────────────────────────

class TestPrefillEndpoint:
    def test_200_for_seeded_task(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert r.status_code == 200

    def test_task_id_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert r.json()["task_id"] == TASK_ID

    def test_readiness_state_present(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert r.json()["readiness_state"] in {"READY", "PARTIAL", "NOT_READY"}

    def test_entities_in_prefill(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert r.json()["entities"]["destination"] == "NYC"

    def test_title_non_empty(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert len(r.json()["title"]) > 0

    def test_missing_inputs_present(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert "passenger_name" in r.json()["missing_inputs"]

    def test_approval_classification_present(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert r.json()["approval_classification"] == "REQUIRES_APPROVAL"

    def test_latency_ms_under_10(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/prefill")
        assert r.json()["latency_ms"] < 10

    def test_404_for_unknown_task(self):
        r = client.get("/unified/tasks/prefill-404/prefill")
        assert r.status_code == 404


# ── GET /unified/tasks/{id}/inspect ──────────────────────────────────────────

class TestInspectEndpoint:
    def test_200_for_task_in_memory(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/inspect")
        assert r.status_code == 200

    def test_task_id_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/inspect")
        assert r.json()["task_id"] == TASK_ID

    def test_state_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/inspect")
        assert r.json()["state"] == TaskState.ready_for_workflow.value

    def test_original_query_in_response(self):
        _seed_task()
        r = client.get(f"/unified/tasks/{TASK_ID}/inspect")
        assert r.json()["original_query"] == "book a flight to NYC"

    def test_inspect_restores_from_db(self):
        """Inspect should fall back to DB restoration if task not in memory."""
        t = UnifiedTask(task_id="insp-db", conversation_id="insp-conv")
        task_persistence.save(t)
        r = client.get("/unified/tasks/insp-db/inspect")
        assert r.status_code == 200
        assert r.json()["task_id"] == "insp-db"

    def test_404_for_unknown_task(self):
        r = client.get("/unified/tasks/inspect-404/inspect")
        assert r.status_code == 404
