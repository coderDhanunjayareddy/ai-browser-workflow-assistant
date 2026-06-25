"""
Integration tests for V5.0 Mission Layer REST endpoints.
Uses FastAPI TestClient with SQLite in-memory DB (test_v50_* prefix → conftest injection).

Endpoints tested:
  POST   /mission/
  GET    /mission/
  GET    /mission/analytics
  POST   /mission/assign
  GET    /mission/{id}
  PATCH  /mission/{id}/state
  DELETE /mission/{id}
  POST   /mission/{id}/tasks/{task_id}
  DELETE /mission/{id}/tasks/{task_id}
  GET    /mission/{id}/timeline
  GET    /mission/{id}/context
  GET    /mission/{id}/memory
  GET    /mission/{id}/restore
  GET    /mission/{id}/bootstrap/{task_id}
  GET    /mission/{id}/inspect
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mission import store as mission_store, analytics as mission_analytics
from app.unified import store as task_store
from app.unified.models import UnifiedTask


@pytest.fixture(autouse=True)
def reset():
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()
    yield
    mission_store._reset_for_testing()
    mission_analytics._reset_for_testing()


@pytest.fixture
def client():
    return TestClient(app)


def _put_task(task_id: str, query: str = "test query") -> None:
    t = UnifiedTask(task_id=task_id, conversation_id="conv-1", original_query=query)
    task_store.put(t)


# ── POST /mission/ ────────────────────────────────────────────────────────────

class TestCreateMission:
    def test_creates_mission(self, client):
        resp = client.post("/mission/", json={"title": "My Mission", "objective": "Test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "My Mission"
        assert data["state"] == "CREATED"

    def test_default_priority(self, client):
        resp = client.post("/mission/", json={"title": "M"})
        assert resp.json()["priority"] == 3

    def test_priority_respected(self, client):
        resp = client.post("/mission/", json={"title": "Urgent", "priority": 1})
        assert resp.json()["priority"] == 1

    def test_returned_fields(self, client):
        resp = client.post("/mission/", json={"title": "M"})
        data = resp.json()
        for field in ["mission_id", "title", "state", "task_ids", "task_count", "created_at"]:
            assert field in data


# ── GET /mission/ ─────────────────────────────────────────────────────────────

class TestListMissions:
    def test_empty_list_initially(self, client):
        resp = client.get("/mission/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_created_mission(self, client):
        client.post("/mission/", json={"title": "M1"})
        resp = client.get("/mission/")
        # CREATED is non-terminal → active_missions returns it
        assert len(resp.json()) == 1


# ── GET /mission/analytics ────────────────────────────────────────────────────

class TestAnalytics:
    def test_analytics_fields(self, client):
        resp = client.get("/mission/analytics")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_missions" in data
        assert "completion_rate" in data or "mission_completion_rate" in data

    def test_analytics_counts_created(self, client):
        client.post("/mission/", json={"title": "M"})
        resp = client.get("/mission/analytics")
        assert resp.json()["total_missions"] == 1


# ── GET /mission/{id} ─────────────────────────────────────────────────────────

class TestGetMission:
    def test_get_existing(self, client):
        created = client.post("/mission/", json={"title": "My M"}).json()
        resp = client.get(f"/mission/{created['mission_id']}")
        assert resp.status_code == 200
        assert resp.json()["mission_id"] == created["mission_id"]

    def test_get_unknown_404(self, client):
        resp = client.get("/mission/ghost-id")
        assert resp.status_code == 404


# ── PATCH /mission/{id}/state ─────────────────────────────────────────────────

class TestUpdateState:
    def _create_active(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        # Attach a task to get to ACTIVE
        _put_task("t-patch")
        client.post(f"/mission/{m['mission_id']}/tasks/t-patch")
        return m["mission_id"]

    def test_pause_active_mission(self, client):
        mid = self._create_active(client)
        resp = client.patch(f"/mission/{mid}/state", json={"action": "pause"})
        assert resp.status_code == 200
        assert resp.json()["state"] == "PAUSED"

    def test_resume_paused_mission(self, client):
        mid = self._create_active(client)
        client.patch(f"/mission/{mid}/state", json={"action": "pause"})
        resp = client.patch(f"/mission/{mid}/state", json={"action": "resume"})
        assert resp.json()["state"] == "ACTIVE"

    def test_complete_active_mission(self, client):
        mid = self._create_active(client)
        resp = client.patch(f"/mission/{mid}/state", json={"action": "complete"})
        assert resp.json()["state"] == "COMPLETED"

    def test_fail_with_reason(self, client):
        mid = self._create_active(client)
        resp = client.patch(f"/mission/{mid}/state", json={"action": "fail", "reason": "DB error"})
        assert resp.json()["state"] == "FAILED"

    def test_invalid_action_400(self, client):
        mid = self._create_active(client)
        resp = client.patch(f"/mission/{mid}/state", json={"action": "teleport"})
        assert resp.status_code == 400


# ── DELETE /mission/{id} ──────────────────────────────────────────────────────

class TestDeleteMission:
    def test_delete_existing(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        resp = client.delete(f"/mission/{m['mission_id']}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_deleted_mission_not_found(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        client.delete(f"/mission/{m['mission_id']}")
        resp = client.get(f"/mission/{m['mission_id']}")
        assert resp.status_code == 404

    def test_delete_unknown_404(self, client):
        resp = client.delete("/mission/ghost-id")
        assert resp.status_code == 404


# ── POST /mission/{id}/tasks/{task_id} ────────────────────────────────────────

class TestAttachTask:
    def test_attach_task(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        _put_task("t-attach")
        resp = client.post(f"/mission/{m['mission_id']}/tasks/t-attach")
        assert resp.status_code == 200
        assert "t-attach" in resp.json()["task_ids"]

    def test_attach_promotes_to_active(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        _put_task("t-active")
        resp = client.post(f"/mission/{m['mission_id']}/tasks/t-active")
        assert resp.json()["state"] == "ACTIVE"

    def test_attach_to_unknown_mission_422(self, client):
        _put_task("t-x")
        resp = client.post("/mission/ghost/tasks/t-x")
        assert resp.status_code == 422


# ── DELETE /mission/{id}/tasks/{task_id} ──────────────────────────────────────

class TestDetachTask:
    def test_detach_task(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        _put_task("t-detach")
        client.post(f"/mission/{m['mission_id']}/tasks/t-detach")
        resp = client.delete(f"/mission/{m['mission_id']}/tasks/t-detach")
        assert resp.status_code == 200
        assert "t-detach" not in resp.json()["task_ids"]


# ── GET /mission/{id}/timeline ────────────────────────────────────────────────

class TestTimeline:
    def test_timeline_returns_list(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        resp = client.get(f"/mission/{m['mission_id']}/timeline")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_timeline_includes_created_event(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        events = client.get(f"/mission/{m['mission_id']}/timeline").json()
        types = [e["event_type"] for e in events]
        assert "mission_created" in types


# ── GET /mission/{id}/context ─────────────────────────────────────────────────

class TestContext:
    def test_context_returns_200(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        resp = client.get(f"/mission/{m['mission_id']}/context")
        assert resp.status_code == 200

    def test_context_fields(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        data = client.get(f"/mission/{m['mission_id']}/context").json()
        assert "task_count" in data
        assert "entities" in data
        assert "memory" in data


# ── GET /mission/{id}/memory ──────────────────────────────────────────────────

class TestMemory:
    def test_memory_returns_200(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        resp = client.get(f"/mission/{m['mission_id']}/memory")
        assert resp.status_code == 200

    def test_memory_mission_id_matches(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        data = client.get(f"/mission/{m['mission_id']}/memory").json()
        assert data["mission_id"] == m["mission_id"]


# ── GET /mission/{id}/restore ─────────────────────────────────────────────────

class TestRestore:
    def test_restore_in_memory_mission(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        resp = client.get(f"/mission/{m['mission_id']}/restore")
        assert resp.status_code == 200

    def test_restore_unknown_404(self, client):
        resp = client.get("/mission/ghost-restore/restore")
        assert resp.status_code == 404


# ── GET /mission/{id}/bootstrap/{task_id} ─────────────────────────────────────

class TestBootstrap:
    def test_bootstrap_returns_200(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        _put_task("t-boot")
        client.post(f"/mission/{m['mission_id']}/tasks/t-boot")
        resp = client.get(f"/mission/{m['mission_id']}/bootstrap/t-boot")
        assert resp.status_code == 200

    def test_bootstrap_enriched_facts_has_mission_id(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        _put_task("t-boot2")
        client.post(f"/mission/{m['mission_id']}/tasks/t-boot2")
        data = client.get(f"/mission/{m['mission_id']}/bootstrap/t-boot2").json()
        assert data["enriched_facts"]["mission_id"] == m["mission_id"]

    def test_bootstrap_unknown_task_404(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        resp = client.get(f"/mission/{m['mission_id']}/bootstrap/ghost-task")
        assert resp.status_code == 404


# ── GET /mission/{id}/inspect ─────────────────────────────────────────────────

class TestInspect:
    def test_inspect_returns_full_view(self, client):
        m = client.post("/mission/", json={"title": "M"}).json()
        resp = client.get(f"/mission/{m['mission_id']}/inspect")
        assert resp.status_code == 200
        data = resp.json()
        assert "mission" in data
        assert "context" in data
        assert "memory" in data
        assert "timeline" in data

    def test_inspect_unknown_404(self, client):
        resp = client.get("/mission/ghost-inspect/inspect")
        assert resp.status_code == 404


# ── POST /mission/assign ──────────────────────────────────────────────────────

class TestAssign:
    def test_assign_creates_new_mission(self, client):
        _put_task("t-assign", "book flight to Paris")
        resp = client.post("/mission/assign", json={"task_id": "t-assign"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == "t-assign"
        assert data["mission_id"] != ""

    def test_assign_unknown_task_404(self, client):
        resp = client.post("/mission/assign", json={"task_id": "ghost"})
        assert resp.status_code == 404

    def test_assign_no_match_create_false(self, client):
        _put_task("t-no-match", "random query with no similarity")
        resp = client.post(
            "/mission/assign",
            json={"task_id": "t-no-match", "create_if_none": False},
        )
        # No match → 404
        assert resp.status_code == 404
