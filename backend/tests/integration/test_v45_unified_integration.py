"""
V4.5 Integration Tests — Unified Task Graph REST API.

Tests cover the /unified/* endpoints via FastAPI TestClient:
  - GET /unified/tasks (empty state)
  - GET /unified/tasks/{id} 404 for unknown
  - GET /unified/tasks/{id} 200 for known task
  - GET /unified/tasks/{id}/context
  - GET /unified/tasks/{id}/timeline
  - POST /unified/tasks/{id}/approvals/{aid}/approve
  - POST /unified/tasks/{id}/approvals/{aid}/deny
  - GET /unified/analytics
  - GET /unified/conversation/{conversation_id}
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.unified import store as task_store, analytics as task_analytics
from app.unified.models import UnifiedTask, TaskState
from app.unified.task_lifecycle import TaskLifecycleManager
from app.unified.approval_center import ApprovalCenter


@pytest.fixture(autouse=True)
def reset_state():
    task_store._reset_for_testing()
    task_analytics._reset_for_testing()
    yield
    task_store._reset_for_testing()
    task_analytics._reset_for_testing()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mgr():
    return TaskLifecycleManager()


@pytest.fixture
def ac():
    return ApprovalCenter()


class TestListTasks:
    def test_empty_list(self, client):
        r = client.get("/unified/tasks")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_task_after_creation(self, client, mgr):
        mgr.create("conv-1", "book flight")
        r = client.get("/unified/tasks")
        assert r.status_code == 200
        assert len(r.json()) == 1


class TestGetTask:
    def test_404_for_unknown_task(self, client):
        r = client.get("/unified/tasks/does-not-exist")
        assert r.status_code == 404

    def test_200_for_known_task(self, client, mgr):
        task = mgr.create("c1", "buy laptop")
        r = client.get(f"/unified/tasks/{task.task_id}")
        assert r.status_code == 200
        data = r.json()
        assert data["task_id"] == task.task_id
        assert data["state"] == "CREATED"

    def test_original_query_returned(self, client, mgr):
        task = mgr.create("c2", "find best laptop")
        r = client.get(f"/unified/tasks/{task.task_id}")
        assert r.json()["original_query"] == "find best laptop"

    def test_conversation_id_returned(self, client, mgr):
        task = mgr.create("conv-check", "q")
        r = client.get(f"/unified/tasks/{task.task_id}")
        assert r.json()["conversation_id"] == "conv-check"


class TestGetContext:
    def test_returns_context_dict(self, client, mgr):
        task = mgr.create("c3", "research topic")
        r = client.get(f"/unified/tasks/{task.task_id}/context")
        assert r.status_code == 200
        data = r.json()
        assert data["task_id"] == task.task_id

    def test_404_for_unknown(self, client):
        r = client.get("/unified/tasks/bad-id/context")
        assert r.status_code == 404


class TestGetTimeline:
    def test_returns_timeline_list(self, client, mgr):
        task = mgr.create("c4", "q")
        r = client.get(f"/unified/tasks/{task.task_id}/timeline")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_user_message_event_present(self, client, mgr):
        task = mgr.create("c5", "my query")
        events = client.get(f"/unified/tasks/{task.task_id}/timeline").json()
        types = [e["type"] for e in events]
        assert "user_message" in types

    def test_404_for_unknown(self, client):
        r = client.get("/unified/tasks/bad-id/timeline")
        assert r.status_code == 404


class TestApproveEndpoint:
    def test_approve_returns_200(self, client, mgr, ac):
        task = mgr.create("c6", "q")
        rec = ac.request(task, "click buy", "HIGH_RISK")
        task_store.put(task)
        r = client.post(f"/unified/tasks/{task.task_id}/approvals/{rec.approval_id}/approve")
        assert r.status_code == 200
        assert r.json()["status"] == "APPROVED"

    def test_approve_unknown_task_returns_404(self, client):
        r = client.post("/unified/tasks/bad-task/approvals/bad-appr/approve")
        assert r.status_code == 404

    def test_approve_unknown_approval_returns_404(self, client, mgr):
        task = mgr.create("c7", "q")
        r = client.post(f"/unified/tasks/{task.task_id}/approvals/bad-appr/approve")
        assert r.status_code == 404


class TestDenyEndpoint:
    def test_deny_returns_200(self, client, mgr, ac):
        task = mgr.create("c8", "q")
        rec = ac.request(task, "delete account", "HIGH_RISK")
        task_store.put(task)
        r = client.post(
            f"/unified/tasks/{task.task_id}/approvals/{rec.approval_id}/deny",
            json={"reason": "too risky"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "DENIED"


class TestAnalyticsEndpoint:
    def test_returns_analytics_dict(self, client):
        r = client.get("/unified/analytics")
        assert r.status_code == 200
        data = r.json()
        assert "total_tasks" in data
        assert "completed_tasks" in data

    def test_increments_reflected(self, client, mgr):
        mgr.create("c9", "q")
        task_analytics.record_task_created()
        r = client.get("/unified/analytics")
        assert r.json()["total_tasks"] >= 1


class TestConversationLookup:
    def test_returns_task_for_conversation(self, client, mgr):
        task = mgr.create("my-conv-123", "q")
        r = client.get("/unified/conversation/my-conv-123")
        assert r.status_code == 200
        assert r.json()["conversation_id"] == "my-conv-123"

    def test_404_for_unknown_conversation(self, client):
        r = client.get("/unified/conversation/no-such-conv")
        assert r.status_code == 404
