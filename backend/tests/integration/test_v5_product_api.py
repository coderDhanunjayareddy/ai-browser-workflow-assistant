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


def test_v5_phase4_billing_api_keys_entitlements_metering_and_budget_alerts(client: TestClient):
    token, _ = register(client, "phase4@example.test")
    headers = auth_headers(token)
    org = client.post("/v5/orgs", json={"name": "Phase Four"}, headers=headers).json()
    workspace = client.post("/v5/workspaces", json={"org_id": org["id"], "name": "Platform APIs"}, headers=headers).json()

    plans = client.get("/v5/billing/plans", headers=headers).json()
    assert {plan["plan_key"] for plan in plans} == {"free", "pro", "team", "enterprise"}
    subscription = client.post("/v5/billing/subscriptions", json={"org_id": org["id"], "plan_key": "team", "seat_count": 3, "trial": True}, headers=headers).json()
    assert subscription["status"] == "trialing"
    assert subscription["seat_count"] == 3
    assert client.get(f"/v5/billing/subscription?org_id={org['id']}", headers=headers).json()["plan_key"] == "team"

    settings = client.patch("/v5/billing/settings", json={"org_id": org["id"], "billing_email": "billing@example.test", "tax_metadata": {"country": "US"}}, headers=headers).json()
    assert settings["billing_email"] == "billing@example.test"
    invoice = client.post("/v5/billing/invoices", json={"org_id": org["id"], "amount_due_cents": 12345, "line_items": [{"label": "Seats", "amount_cents": 12345}]}, headers=headers).json()
    assert invoice["amount_due_cents"] == 12345
    assert client.get(f"/v5/billing/invoices?org_id={org['id']}", headers=headers).json()[0]["invoice_number"] == invoice["invoice_number"]

    created_key = client.post("/v5/api-keys", json={"org_id": org["id"], "workspace_id": workspace["id"], "name": "CI key", "scopes": ["workflow:run"]}, headers=headers).json()
    assert created_key["secret"].startswith("v5_")
    key = created_key["api_key"]
    assert key["key_preview"].startswith("v5_")
    assert "..." in key["key_preview"]
    assert "key_hash" not in key
    touched = client.post(f"/v5/api-keys/{key['id']}/touch", headers=headers).json()
    assert touched["usage_count"] == 1
    rotated = client.post(f"/v5/api-keys/{key['id']}/rotate", headers=headers).json()
    assert rotated["secret"].startswith("v5_")
    revoked = client.post(f"/v5/api-keys/{rotated['api_key']['id']}/revoke", headers=headers).json()
    assert revoked["status"] == "revoked"

    client.post("/v5/usage/records", json={"org_id": org["id"], "workspace_id": workspace["id"], "usage_type": "token_usage", "quantity": 250, "unit": "tokens"}, headers=headers)
    rollups = client.get(f"/v5/usage/rollups?org_id={org['id']}", headers=headers).json()
    assert {rollup["usage_type"] for rollup in rollups} >= {"api_usage", "token_usage"}
    entitlement = client.get(f"/v5/entitlements?org_id={org['id']}", headers=headers).json()
    assert entitlement["plan_key"] == "team"
    assert entitlement["enforcement"]["runtime_enforced"] is False

    alert = client.post("/v5/budget-alerts", json={"org_id": org["id"], "workspace_id": workspace["id"], "name": "Monthly API budget", "monthly_budget_cents": 5000, "threshold_percent": 80}, headers=headers).json()
    assert alert["monthly_budget_cents"] == 5000
    assert client.get(f"/v5/budget-alerts?org_id={org['id']}", headers=headers).json()[0]["id"] == alert["id"]
    notifications = client.get("/v5/notifications", headers=headers).json()
    assert "budget_alert.created" in {item["event_type"] for item in notifications}


def test_v5_phase5_enterprise_readiness_admin_security_and_governance(client: TestClient):
    token, _ = register(client, "phase5@example.test")
    headers = auth_headers(token)
    org = client.post("/v5/orgs", json={"name": "Phase Five"}, headers=headers).json()
    workspace = client.post("/v5/workspaces", json={"org_id": org["id"], "name": "Enterprise"}, headers=headers).json()

    sso = client.patch("/v5/enterprise/sso", json={
        "org_id": org["id"],
        "saml_metadata": {"entity_id": "stub-saml"},
        "oidc_metadata": {"issuer": "stub-issuer"},
        "idp_metadata": {"provider": "stub"},
        "login_policy": {"mode": "sso_required"},
        "domain_verification": {"domain": "example.test", "status": "verified"},
        "enforce_sso": True,
    }, headers=headers).json()
    assert sso["enforce_sso"] is True
    assert client.get(f"/v5/enterprise/sso?org_id={org['id']}", headers=headers).json()["provider_mode"] == "stub"

    scim = client.patch("/v5/enterprise/scim", json={
        "org_id": org["id"],
        "base_url": "https://scim.example.test/v2",
        "bearer_token": "secret-token",
        "user_mapping": {"email": "userName"},
        "group_mapping": {"name": "displayName"},
    }, headers=headers).json()
    assert scim["provisioning_status"] == "enabled"
    assert "bearer_token_hash" not in scim
    sync = client.post("/v5/enterprise/scim/sync-events", json={"org_id": org["id"], "resource_type": "user", "external_id": "u-1", "action": "provision"}, headers=headers).json()
    assert sync["action"] == "provision"

    policy = client.post("/v5/enterprise/security-policies", json={
        "org_id": org["id"],
        "workspace_id": workspace["id"],
        "policy_type": "mfa",
        "name": "Require MFA",
        "rules": {"mfa_required": True, "session_timeout_minutes": 60},
    }, headers=headers).json()
    assert policy["current_version"] == 1
    assert client.get(f"/v5/enterprise/security-policies?org_id={org['id']}", headers=headers).json()[0]["id"] == policy["id"]

    export = client.post("/v5/enterprise/compliance-exports", json={"org_id": org["id"], "export_type": "audit_logs", "filters": {"risk": "high"}}, headers=headers).json()
    assert export["status"] == "completed"
    assert export["artifact_ref"].startswith("stub-export:")
    retention = client.post("/v5/enterprise/retention-rules", json={"org_id": org["id"], "workspace_id": workspace["id"], "data_type": "replay_metadata", "retention_days": 90}, headers=headers).json()
    assert retention["retention_days"] == 90

    client.patch("/v5/enterprise/governance/settings", json={"org_id": org["id"], "settings": {"high_risk_requires_approval": True}}, headers=headers)
    workflow = client.post("/v5/enterprise/governance/workflows", json={"org_id": org["id"], "workspace_id": workspace["id"], "name": "High risk approval", "trigger_policy": {"risk": "high"}, "approver_rules": {"role": "admin"}}, headers=headers).json()
    assert workflow["status"] == "active"
    governance = client.get(f"/v5/enterprise/governance-dashboard?org_id={org['id']}", headers=headers).json()
    assert governance["v3_governance_ref"] == "v3-governance"
    assert governance["approval_workflows"][0]["name"] == "High risk approval"

    security = client.get(f"/v5/enterprise/security-dashboard?org_id={org['id']}", headers=headers).json()
    assert security["security_score"] < 100
    assert security["risk_summary"]["high"] >= 1
    audit = client.get(f"/v5/enterprise/audit?org_id={org['id']}&risk=high", headers=headers).json()
    assert any(record["event_type"] == "compliance.export.created" for record in audit)
    assert audit[0]["immutable_hash"]

    admin = client.get(f"/v5/enterprise/admin-portal?org_id={org['id']}", headers=headers).json()
    assert admin["users"] == 1
    assert admin["workspaces"] == 1
    assert admin["feature_flags"]["enterprise_governance"] == "metadata_only"
