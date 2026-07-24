from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app as fastapi_app
import app.product.models  # noqa: F401


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register(client: TestClient, email: str) -> tuple[str, dict]:
    res = client.post("/v5/auth/register", json={"email": email, "password": "password123", "name": email.split("@")[0]})
    assert res.status_code == 200, res.text
    data = res.json()
    return data["token"], data["user"]


def test_v5_phase1_auth_org_workspace_workflow_settings_and_audit(client: TestClient):
    token, user = register(client, "ada@example.test")
    headers = auth_headers(token)

    assert client.get("/v5/me", headers=headers).json()["email"] == "ada@example.test"

    org = client.post("/v5/orgs", json={"name": "Ada Labs"}, headers=headers).json()
    assert org["role"] == "owner"
    assert client.get("/v5/orgs", headers=headers).json()[0]["id"] == org["id"]

    team = client.post(f"/v5/orgs/{org['id']}/teams", json={"name": "Automation"}, headers=headers).json()
    assert team["name"] == "Automation"

    workspace = client.post("/v5/workspaces", json={"org_id": org["id"], "name": "Launch"}, headers=headers).json()
    assert workspace["role"] == "owner"

    updated = client.patch(f"/v5/workspaces/{workspace['id']}/settings", json={"settings": {"retention_days": 14}}, headers=headers).json()
    assert updated["settings"]["retention_days"] == 14

    pref = client.patch("/v5/me/preferences", json={"settings": {"theme": "dark"}}, headers=headers).json()
    assert pref["preferences"]["theme"] == "dark"

    run = client.post("/v5/workflows", json={
        "workspace_id": workspace["id"],
        "title": "Check release",
        "status": "completed",
        "input_summary": "Open release page",
        "output_summary": "Release page checked",
        "runtime_ref": "v3-run-1",
        "browser_session_ref": "v4-session-1",
        "steps": [{"action_type": "navigate", "status": "completed", "capability_id": "browser.navigation"}],
    }, headers=headers).json()
    assert run["title"] == "Check release"
    assert run["steps"][0]["action_type"] == "navigate"

    history = client.get("/v5/workflows", headers=headers).json()
    assert len(history) == 1
    assert history[0]["id"] == run["id"]
    assert client.get(f"/v5/workflows/{run['id']}", headers=headers).json()["output_summary"] == "Release page checked"

    audit = client.get(f"/v5/audit-logs?org_id={org['id']}", headers=headers).json()
    assert {event["event_type"] for event in audit} >= {"org.created", "workspace.created", "workflow.created"}

    logout = client.post("/v5/auth/logout", headers=headers)
    assert logout.status_code == 200
    assert client.get("/v5/me", headers=headers).status_code == 401
    assert user["id"]


def test_v5_workspace_and_org_isolation(client: TestClient):
    token_a, _ = register(client, "ada@example.test")
    token_b, _ = register(client, "grace@example.test")
    headers_a = auth_headers(token_a)
    headers_b = auth_headers(token_b)

    org = client.post("/v5/orgs", json={"name": "Private Org"}, headers=headers_a).json()
    workspace = client.post("/v5/workspaces", json={"org_id": org["id"], "name": "Private Workspace"}, headers=headers_a).json()
    run = client.post("/v5/workflows", json={"workspace_id": workspace["id"], "title": "Secret"}, headers=headers_a).json()

    assert client.post("/v5/workspaces", json={"org_id": org["id"], "name": "Intrude"}, headers=headers_b).status_code == 403
    assert client.get(f"/v5/workflows/{run['id']}", headers=headers_b).status_code == 404
    assert client.get(f"/v5/orgs/{org['id']}/teams", headers=headers_b).status_code == 403


def test_v5_phase2_replay_tasks_templates_versions_notifications_and_rerun(client: TestClient):
    token, _ = register(client, "phase2@example.test")
    headers = auth_headers(token)
    org = client.post("/v5/orgs", json={"name": "Phase Two"}, headers=headers).json()
    workspace = client.post("/v5/workspaces", json={"org_id": org["id"], "name": "Reusable Work"}, headers=headers).json()

    run = client.post("/v5/workflows", json={
        "workspace_id": workspace["id"],
        "title": "Reusable workflow",
        "status": "completed",
        "input_summary": "Do the reusable thing",
        "output_summary": "Done",
        "parameters": {"target": "docs"},
        "runtime_ref": "v3-ledger-22",
        "browser_session_ref": "v4-replay-22",
        "steps": [{
            "step_index": 0,
            "action_type": "click",
            "status": "completed",
            "validation_status": "verified",
            "metadata": {
                "screenshot_ref": "shot-1",
                "visual_region": {"x": 1, "y": 2, "width": 3, "height": 4},
                "governance": {"decision": "allowed"},
                "password": "secret",
            },
        }],
    }, headers=headers).json()
    assert run["parameters"]["target"] == "docs"

    replay = client.get(f"/v5/workflows/{run['id']}/replay", headers=headers).json()
    assert replay["workflow"]["runtime_ref"] == "v3-ledger-22"
    assert replay["timeline"][0]["screenshot_ref"] == "shot-1"
    assert replay["timeline"][0]["metadata"]["password"] == "[redacted]"

    share = client.post(f"/v5/workflows/{run['id']}/replay/share", json={"visibility": "workspace"}, headers=headers).json()
    assert share["workflow_run_id"] == run["id"]
    assert share["share_token"]

    cloned = client.post(f"/v5/workflows/{run['id']}/clone", headers=headers).json()
    rerun = client.post(f"/v5/workflows/{run['id']}/rerun", headers=headers).json()
    assert cloned["parameters"]["target"] == "docs"
    assert rerun["status"] == "queued"
    assert rerun["steps"][0]["status"] == "pending"

    task = client.post("/v5/tasks", json={
        "workspace_id": workspace["id"],
        "scope": "workspace",
        "title": "Saved launch check",
        "input_prompt": "Check launch readiness",
        "tags": ["launch", "qa"],
        "favorite": True,
    }, headers=headers).json()
    assert task["favorite"] is True
    assert client.get("/v5/tasks?q=launch&tag=qa", headers=headers).json()[0]["id"] == task["id"]
    task_run = client.post(f"/v5/tasks/{task['id']}/run", json={}, headers=headers).json()
    assert task_run["status"] == "queued"

    template = client.post("/v5/templates", json={
        "workspace_id": workspace["id"],
        "title": "Weekly report",
        "description": "Reusable report",
        "parameter_schema": {"type": "object", "properties": {"week": {"type": "string"}}},
        "body": {"prompt": "Build weekly report"},
    }, headers=headers).json()
    assert template["current_version"] == 1
    updated = client.patch(f"/v5/templates/{template['id']}", json={"description": "Updated", "change_summary": "Tighten description"}, headers=headers).json()
    assert updated["current_version"] == 2
    assert len(client.get(f"/v5/templates/{template['id']}/versions", headers=headers).json()) == 2
    assert client.post(f"/v5/templates/{template['id']}/run", json={"parameters": {"week": "2026-W30"}}, headers=headers).json()["parameters"]["week"] == "2026-W30"
    assert client.post(f"/v5/templates/{template['id']}/fork", json={}, headers=headers).json()["forked_from_template_id"] == template["id"]

    versions = client.get(f"/v5/versions/template/{template['id']}", headers=headers).json()
    assert [version["version_number"] for version in versions] == [2, 1]
    assert "description" in versions[0]["diff"]["changed"]

    custom_version = client.post("/v5/versions", json={
        "workspace_id": workspace["id"],
        "resource_type": "saved_task",
        "resource_id": task["id"],
        "snapshot": {"title": task["title"]},
        "change_summary": "Manual checkpoint",
    }, headers=headers).json()
    assert custom_version["version_number"] == 1

    notifications = client.get("/v5/notifications", headers=headers).json()
    assert {item["event_type"] for item in notifications} >= {"workflow.completed", "workflow.rerun.queued"}
    unread = [item for item in notifications if not item["read_at"]]
    marked = client.post(f"/v5/notifications/{unread[0]['id']}/read", headers=headers).json()
    assert marked["read_at"]


def test_v5_phase3_collaboration_assistants_integrations_analytics_and_usage(client: TestClient):
    token, user = register(client, "phase3@example.test")
    headers = auth_headers(token)
    org = client.post("/v5/orgs", json={"name": "Phase Three"}, headers=headers).json()
    workspace = client.post("/v5/workspaces", json={"org_id": org["id"], "name": "Collab Space"}, headers=headers).json()

    team = client.post(f"/v5/orgs/{org['id']}/teams", json={"name": "Operators"}, headers=headers).json()
    assert team["name"] == "Operators"
    members = client.get(f"/v5/teams/{team['id']}/members", headers=headers).json()
    assert members[0]["user_id"] == user["id"]
    member = client.post(f"/v5/teams/{team['id']}/members", json={"user_id": user["id"], "role": "admin"}, headers=headers).json()
    assert member["role"] == "admin"

    invite = client.post("/v5/invitations", json={"org_id": org["id"], "team_id": team["id"], "workspace_id": workspace["id"], "email": "new@example.test"}, headers=headers).json()
    assert invite["status"] == "pending"
    share = client.post(f"/v5/workspaces/{workspace['id']}/shares", json={"team_id": team["id"], "role": "member"}, headers=headers).json()
    assert share["team_id"] == team["id"]
    activity = client.get(f"/v5/orgs/{org['id']}/activity", headers=headers).json()
    assert {item["activity_type"] for item in activity} >= {"team.created", "workspace.shared", "invitation.created"}

    assistant = client.post("/v5/assistants", json={
        "org_id": org["id"],
        "name": "Release Assistant",
        "instructions": "Help with release workflows",
        "capability_permissions": ["workflow.run", "browser.observe"],
    }, headers=headers).json()
    assert assistant["current_version"] == 1
    updated = client.patch(f"/v5/assistants/{assistant['id']}", json={"description": "Updated", "change_summary": "Add description"}, headers=headers).json()
    assert updated["current_version"] == 2
    assert client.post(f"/v5/assistants/{assistant['id']}/publish", headers=headers).json()["status"] == "published"
    assignment = client.post(f"/v5/assistants/{assistant['id']}/assignments", json={"workspace_id": workspace["id"]}, headers=headers).json()
    assert assignment["workspace_id"] == workspace["id"]
    assert len(client.get(f"/v5/assistants/{assistant['id']}/versions", headers=headers).json()) == 2

    catalog = client.get("/v5/integrations/catalog", headers=headers).json()
    assert {item["provider_key"] for item in catalog} >= {"github", "slack"}
    connection = client.post("/v5/integrations/connections", json={"org_id": org["id"], "workspace_id": workspace["id"], "provider_key": "github"}, headers=headers).json()
    assert connection["provider_key"] == "github"
    health = client.post(f"/v5/integrations/connections/{connection['id']}/health", json={"status": "healthy", "latency_ms": 42}, headers=headers).json()
    assert health["status"] == "healthy"

    client.post("/v5/workflows", json={
        "workspace_id": workspace["id"],
        "title": "Analytics workflow",
        "status": "completed",
        "steps": [{"capability_id": "browser.navigation", "action_type": "navigate"}],
    }, headers=headers)
    client.post("/v5/usage/records", json={"org_id": org["id"], "workspace_id": workspace["id"], "usage_type": "token_usage", "quantity": 150, "unit": "tokens"}, headers=headers)
    client.post("/v5/usage/records", json={"org_id": org["id"], "workspace_id": workspace["id"], "usage_type": "api_usage", "quantity": 3, "unit": "requests"}, headers=headers)

    analytics = client.get(f"/v5/analytics?org_id={org['id']}", headers=headers).json()
    assert analytics["workflow_status"]["completed"] == 1
    assert analytics["capability_usage"]["browser.navigation"] == 1
    assert analytics["success_rate"] == 1.0

    usage = client.get(f"/v5/usage?org_id={org['id']}", headers=headers).json()
    assert usage["totals"]["token_usage"] == 150
    assert usage["totals"]["api_usage"] == 3
