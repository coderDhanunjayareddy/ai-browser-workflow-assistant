from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.product.dependencies import ProductPrincipal, current_principal
from app.product.repositories import ProductRepository
from app.product.schemas import (
    AdvancedAuditOut,
    AdminPortalOut,
    AnalyticsOut,
    ApiKeyCreate,
    ApiKeyCreateOut,
    ApiKeyOut,
    AuditOut,
    AssistantAssignRequest,
    AssistantAssignmentOut,
    AssistantCreate,
    AssistantOut,
    AssistantUpdate,
    AssistantVersionOut,
    BillingPlanOut,
    BillingSettingsOut,
    BillingSettingsUpdate,
    BudgetAlertCreate,
    BudgetAlertOut,
    ComplianceExportCreate,
    ComplianceExportOut,
    EntitlementOut,
    GovernanceDashboardOut,
    GovernanceSettingsUpdate,
    GovernanceWorkflowCreate,
    GovernanceWorkflowOut,
    IntegrationCatalogOut,
    IntegrationConnectRequest,
    IntegrationConnectionOut,
    IntegrationHealthOut,
    IntegrationHealthRequest,
    InvoiceCreate,
    InvoiceOut,
    InvitationCreate,
    InvitationOut,
    LoginRequest,
    NotificationOut,
    OrganizationCreate,
    OrganizationOut,
    RegisterRequest,
    ReplayOut,
    ReplayShareCreate,
    ReplayShareOut,
    ResourceVersionCreate,
    ResourceVersionOut,
    RetentionRuleCreate,
    RetentionRuleOut,
    SavedTaskCreate,
    SavedTaskOut,
    SavedTaskUpdate,
    SettingsUpdate,
    ScimConfigOut,
    ScimConfigUpdate,
    ScimSyncCreate,
    ScimSyncOut,
    SecurityDashboardOut,
    SecurityPolicyCreate,
    SecurityPolicyOut,
    SsoConfigOut,
    SsoConfigUpdate,
    SubscriptionCreate,
    SubscriptionOut,
    TaskRunRequest,
    TeamActivityOut,
    TeamCreate,
    TeamMemberAdd,
    TeamMemberOut,
    TeamOut,
    TemplateCreate,
    TemplateForkRequest,
    TemplateOut,
    TemplateRunRequest,
    TemplateUpdate,
    TemplateVersionOut,
    TokenResponse,
    UsageDashboardOut,
    UsageRecordCreate,
    UsageRollupOut,
    UserOut,
    WorkflowCreate,
    WorkflowOut,
    WorkspaceCreate,
    WorkspaceShareCreate,
    WorkspaceShareOut,
    WorkspaceOut,
)
from app.product.serializers import (
    advanced_audit_out,
    assistant_assignment_out,
    assistant_out,
    assistant_version_out,
    api_key_out,
    audit_out,
    billing_plan_out,
    billing_settings_out,
    budget_alert_out,
    compliance_export_out,
    entitlement_out,
    governance_workflow_out,
    integration_catalog_out,
    integration_connection_out,
    integration_health_out,
    invitation_out,
    invoice_out,
    notification_out,
    org_out,
    replay_share_out,
    resource_version_out,
    retention_rule_out,
    saved_task_out,
    scim_config_out,
    scim_sync_out,
    security_policy_out,
    sso_config_out,
    team_activity_out,
    team_member_out,
    team_out,
    template_out,
    template_version_out,
    subscription_out,
    usage_rollup_out,
    user_out,
    workflow_out,
    workspace_share_out,
    workspace_out,
)
from app.product.services import ProductService


router = APIRouter(prefix="/v5", tags=["v5-product"])


@router.post("/auth/register", response_model=TokenResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    user, token = ProductService(db).register(email=payload.email, password=payload.password, name=payload.name)
    return {"token": token, "token_type": "bearer", "user": user_out(user)}


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user, token = ProductService(db).login(email=payload.email, password=payload.password)
    return {"token": token, "token_type": "bearer", "user": user_out(user)}


@router.post("/auth/logout")
def logout(principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    ProductService(db).logout(session_id=principal.session.id, user_id=principal.user.id)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(principal: ProductPrincipal = Depends(current_principal)) -> dict:
    return user_out(principal.user)


@router.patch("/me/preferences")
def update_preferences(payload: SettingsUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    pref = ProductService(db).update_user_preferences(user=principal.user, preferences=payload.settings)
    return {"preferences": pref.preferences}


@router.post("/orgs", response_model=OrganizationOut)
def create_org(payload: OrganizationCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    org = ProductService(db).create_org(user=principal.user, name=payload.name, slug=payload.slug)
    return org_out(org, "owner")


@router.get("/orgs", response_model=list[OrganizationOut])
def list_orgs(principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    repo = ProductRepository(db)
    return [org_out(org, repo.org_role(org.id, principal.user.id)) for org in repo.list_user_orgs(principal.user.id)]


@router.post("/orgs/{org_id}/teams", response_model=TeamOut)
def create_team(org_id: str, payload: TeamCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return team_out(ProductService(db).create_team(user=principal.user, org_id=org_id, name=payload.name))


@router.get("/orgs/{org_id}/teams", response_model=list[TeamOut])
def list_teams(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_member(principal.user.id, org_id)
    return [team_out(team) for team in service.repo.list_teams(org_id)]


@router.post("/teams/{team_id}/members", response_model=TeamMemberOut)
def add_team_member(team_id: str, payload: TeamMemberAdd, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return team_member_out(ProductService(db).add_team_member(user=principal.user, team_id=team_id, member_user_id=payload.user_id, role=payload.role))


@router.get("/teams/{team_id}/members", response_model=list[TeamMemberOut])
def list_team_members(team_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    team = service.repo.get_team(team_id)
    if not team:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="team not found")
    service.require_org_member(principal.user.id, team.org_id)
    return [team_member_out(member) for member in service.repo.list_team_members(team_id)]


@router.post("/invitations", response_model=InvitationOut)
def create_invitation(payload: InvitationCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return invitation_out(ProductService(db).invite_user(user=principal.user, data=payload.model_dump()))


@router.get("/orgs/{org_id}/invitations", response_model=list[InvitationOut])
def list_invitations(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    return [invitation_out(invitation) for invitation in service.repo.list_invitations(org_id=org_id)]


@router.get("/orgs/{org_id}/activity", response_model=list[TeamActivityOut])
def team_activity(org_id: str, team_id: str | None = None, limit: int = Query(default=50, ge=1, le=100), principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_member(principal.user.id, org_id)
    return [team_activity_out(activity) for activity in service.repo.list_team_activity(org_id=org_id, team_id=team_id, limit=limit)]


@router.post("/workspaces", response_model=WorkspaceOut)
def create_workspace(payload: WorkspaceCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    workspace = ProductService(db).create_workspace(user=principal.user, org_id=payload.org_id, name=payload.name, description=payload.description)
    return workspace_out(workspace, "owner")


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(org_id: str | None = None, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    repo = ProductRepository(db)
    return [workspace_out(workspace, repo.workspace_role(workspace.id, principal.user.id)) for workspace in repo.list_workspaces(user_id=principal.user.id, org_id=org_id)]


@router.patch("/workspaces/{workspace_id}/settings")
def update_workspace_settings(workspace_id: str, payload: SettingsUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    settings = ProductService(db).update_workspace_settings(user=principal.user, workspace_id=workspace_id, settings=payload.settings)
    return {"settings": settings.settings}


@router.post("/workspaces/{workspace_id}/shares", response_model=WorkspaceShareOut)
def share_workspace(workspace_id: str, payload: WorkspaceShareCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return workspace_share_out(ProductService(db).share_workspace(user=principal.user, workspace_id=workspace_id, team_id=payload.team_id, role=payload.role))


@router.post("/workflows", response_model=WorkflowOut)
def create_workflow(payload: WorkflowCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    run = ProductService(db).create_workflow_run(user=principal.user, workspace_id=payload.workspace_id, data=payload.model_dump())
    return workflow_out(run)


@router.get("/workflows", response_model=list[WorkflowOut])
def list_workflows(
    workspace_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    principal: ProductPrincipal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    repo = ProductRepository(db)
    if workspace_id:
        ProductService(db).require_workspace_role(principal.user.id, workspace_id, {"owner", "admin", "member", "viewer"})
    return [workflow_out(run) for run in repo.list_workflow_runs(user_id=principal.user.id, workspace_id=workspace_id, limit=limit)]


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    run = ProductRepository(db).get_workflow_run_for_user(workflow_id, principal.user.id)
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="workflow not found")
    return workflow_out(run)


@router.post("/workflows/{workflow_id}/clone", response_model=WorkflowOut)
def clone_workflow(workflow_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return workflow_out(ProductService(db).clone_workflow_run(user=principal.user, workflow_id=workflow_id, rerun=False))


@router.post("/workflows/{workflow_id}/rerun", response_model=WorkflowOut)
def rerun_workflow(workflow_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return workflow_out(ProductService(db).clone_workflow_run(user=principal.user, workflow_id=workflow_id, rerun=True))


@router.get("/workflows/{workflow_id}/replay", response_model=ReplayOut)
def workflow_replay(workflow_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return ProductService(db).replay_for_workflow(user=principal.user, workflow_id=workflow_id)


@router.post("/workflows/{workflow_id}/replay/share", response_model=ReplayShareOut)
def share_workflow_replay(workflow_id: str, payload: ReplayShareCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    share = ProductService(db).create_replay_share(user=principal.user, workflow_id=workflow_id, visibility=payload.visibility, redaction_policy=payload.redaction_policy)
    return replay_share_out(share)


@router.post("/tasks", response_model=SavedTaskOut)
def create_saved_task(payload: SavedTaskCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return saved_task_out(ProductService(db).create_saved_task(user=principal.user, data=payload.model_dump()))


@router.get("/tasks", response_model=list[SavedTaskOut])
def list_saved_tasks(
    q: str = "",
    tag: str = "",
    limit: int = Query(default=50, ge=1, le=100),
    principal: ProductPrincipal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    repo = ProductRepository(db)
    workspaces = repo.list_workspaces(user_id=principal.user.id)
    return [saved_task_out(task) for task in repo.list_saved_tasks(user_id=principal.user.id, workspace_ids=[workspace.id for workspace in workspaces], query=q, tag=tag, limit=limit)]


@router.patch("/tasks/{task_id}", response_model=SavedTaskOut)
def update_saved_task(task_id: str, payload: SavedTaskUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    data = payload.model_dump(exclude_unset=True)
    return saved_task_out(ProductService(db).update_saved_task(user=principal.user, task_id=task_id, data=data))


@router.post("/tasks/{task_id}/run", response_model=WorkflowOut)
def run_saved_task(task_id: str, payload: TaskRunRequest, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return workflow_out(ProductService(db).run_saved_task(user=principal.user, task_id=task_id, workspace_id=payload.workspace_id))


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return template_out(ProductService(db).create_template(user=principal.user, workspace_id=payload.workspace_id, data=payload.model_dump()))


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    q: str = "",
    limit: int = Query(default=50, ge=1, le=100),
    principal: ProductPrincipal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    repo = ProductRepository(db)
    workspaces = repo.list_workspaces(user_id=principal.user.id)
    return [template_out(template) for template in repo.list_templates(workspace_ids=[workspace.id for workspace in workspaces], query=q, limit=limit)]


@router.patch("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: str, payload: TemplateUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return template_out(ProductService(db).update_template(user=principal.user, template_id=template_id, data=payload.model_dump(exclude_unset=True)))


@router.post("/templates/{template_id}/run", response_model=WorkflowOut)
def run_template(template_id: str, payload: TemplateRunRequest, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return workflow_out(ProductService(db).run_template(user=principal.user, template_id=template_id, parameters=payload.parameters))


@router.post("/templates/{template_id}/fork", response_model=TemplateOut)
def fork_template(template_id: str, payload: TemplateForkRequest, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return template_out(ProductService(db).fork_template(user=principal.user, template_id=template_id, workspace_id=payload.workspace_id))


@router.get("/templates/{template_id}/versions", response_model=list[TemplateVersionOut])
def list_template_versions(template_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    template = service.require_template_access(principal.user.id, template_id, write=False)
    return [template_version_out(version) for version in sorted(template.versions, key=lambda item: item.version_number, reverse=True)]


@router.post("/versions", response_model=ResourceVersionOut)
def create_resource_version(payload: ResourceVersionCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return resource_version_out(ProductService(db).create_resource_version(user=principal.user, data=payload.model_dump()))


@router.get("/versions/{resource_type}/{resource_id}", response_model=list[ResourceVersionOut])
def list_resource_versions(resource_type: str, resource_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    repo = ProductRepository(db)
    versions = repo.list_resource_versions(resource_type=resource_type, resource_id=resource_id)
    visible = []
    service = ProductService(db)
    for version in versions:
        if version.workspace_id:
            service.require_workspace_role(principal.user.id, version.workspace_id, {"owner", "admin", "member", "viewer"})
        elif version.org_id:
            service.require_org_member(principal.user.id, version.org_id)
        visible.append(resource_version_out(version))
    return visible


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=100),
    principal: ProductPrincipal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [notification_out(item) for item in ProductRepository(db).list_notifications(user_id=principal.user.id, unread_only=unread_only, limit=limit)]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(notification_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return notification_out(ProductService(db).mark_notification_read(user=principal.user, notification_id=notification_id))


@router.post("/assistants", response_model=AssistantOut)
def create_assistant(payload: AssistantCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return assistant_out(ProductService(db).create_assistant(user=principal.user, data=payload.model_dump()))


@router.get("/assistants", response_model=list[AssistantOut])
def list_assistants(limit: int = Query(default=50, ge=1, le=100), principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    repo = ProductRepository(db)
    orgs = repo.list_user_orgs(principal.user.id)
    return [assistant_out(assistant) for assistant in repo.list_assistants(org_ids=[org.id for org in orgs], limit=limit)]


@router.patch("/assistants/{assistant_id}", response_model=AssistantOut)
def update_assistant(assistant_id: str, payload: AssistantUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return assistant_out(ProductService(db).update_assistant(user=principal.user, assistant_id=assistant_id, data=payload.model_dump(exclude_unset=True)))


@router.post("/assistants/{assistant_id}/publish", response_model=AssistantOut)
def publish_assistant(assistant_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return assistant_out(ProductService(db).set_assistant_status(user=principal.user, assistant_id=assistant_id, status_value="published"))


@router.post("/assistants/{assistant_id}/unpublish", response_model=AssistantOut)
def unpublish_assistant(assistant_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return assistant_out(ProductService(db).set_assistant_status(user=principal.user, assistant_id=assistant_id, status_value="draft"))


@router.post("/assistants/{assistant_id}/assignments", response_model=AssistantAssignmentOut)
def assign_assistant(assistant_id: str, payload: AssistantAssignRequest, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return assistant_assignment_out(ProductService(db).assign_assistant(user=principal.user, assistant_id=assistant_id, workspace_id=payload.workspace_id, role=payload.role))


@router.get("/assistants/{assistant_id}/versions", response_model=list[AssistantVersionOut])
def assistant_versions(assistant_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    assistant = service.require_assistant_access(principal.user.id, assistant_id, write=False)
    return [assistant_version_out(version) for version in sorted(assistant.versions, key=lambda item: item.version_number, reverse=True)]


@router.get("/integrations/catalog", response_model=list[IntegrationCatalogOut])
def integration_catalog(principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    return [integration_catalog_out(item) for item in ProductRepository(db).ensure_integration_catalog()]


@router.post("/integrations/connections", response_model=IntegrationConnectionOut)
def connect_integration(payload: IntegrationConnectRequest, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return integration_connection_out(ProductService(db).connect_integration(user=principal.user, data=payload.model_dump()))


@router.get("/integrations/connections", response_model=list[IntegrationConnectionOut])
def list_integrations(principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    repo = ProductRepository(db)
    orgs = repo.list_user_orgs(principal.user.id)
    return [integration_connection_out(connection) for connection in repo.list_integration_connections(org_ids=[org.id for org in orgs])]


@router.post("/integrations/connections/{connection_id}/health", response_model=IntegrationHealthOut)
def integration_health(connection_id: str, payload: IntegrationHealthRequest, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return integration_health_out(ProductService(db).record_integration_health(user=principal.user, connection_id=connection_id, status_value=payload.status, latency_ms=payload.latency_ms, message=payload.message))


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return ProductService(db).analytics_dashboard(user=principal.user, org_id=org_id)


@router.post("/usage/records")
def create_usage_record(payload: UsageRecordCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    record = ProductService(db).create_usage_record(user=principal.user, data=payload.model_dump())
    return {"id": record.id}


@router.get("/usage", response_model=UsageDashboardOut)
def usage_dashboard(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return ProductService(db).usage_dashboard(user=principal.user, org_id=org_id)


@router.get("/billing/plans", response_model=list[BillingPlanOut])
def billing_plans(db: Session = Depends(get_db)) -> list[dict]:
    return [billing_plan_out(plan) for plan in ProductRepository(db).ensure_billing_plans()]


@router.post("/billing/subscriptions", response_model=SubscriptionOut)
def create_subscription(payload: SubscriptionCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return subscription_out(ProductService(db).create_subscription(user=principal.user, data=payload.model_dump()))


@router.get("/billing/subscription", response_model=SubscriptionOut | None)
def get_subscription(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict | None:
    service = ProductService(db)
    service.require_org_member(principal.user.id, org_id)
    subscription = service.repo.get_subscription(org_id)
    return subscription_out(subscription) if subscription else None


@router.patch("/billing/settings", response_model=BillingSettingsOut)
def update_billing_settings(payload: BillingSettingsUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return billing_settings_out(ProductService(db).update_billing_settings(user=principal.user, data=payload.model_dump()))


@router.post("/billing/invoices", response_model=InvoiceOut)
def create_invoice(payload: InvoiceCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return invoice_out(ProductService(db).create_invoice(user=principal.user, data=payload.model_dump()))


@router.get("/billing/invoices", response_model=list[InvoiceOut])
def list_invoices(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_member(principal.user.id, org_id)
    return [invoice_out(invoice) for invoice in service.repo.list_invoices(org_id=org_id)]


@router.post("/api-keys", response_model=ApiKeyCreateOut)
def create_api_key(payload: ApiKeyCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    key, secret = ProductService(db).create_api_key(user=principal.user, data=payload.model_dump())
    return {"api_key": api_key_out(key), "secret": secret}


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    repo = ProductRepository(db)
    orgs = repo.list_user_orgs(principal.user.id)
    return [api_key_out(key) for key in repo.list_api_keys(org_ids=[org.id for org in orgs])]


@router.post("/api-keys/{key_id}/rotate", response_model=ApiKeyCreateOut)
def rotate_api_key(key_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    key, secret = ProductService(db).rotate_api_key(user=principal.user, key_id=key_id)
    return {"api_key": api_key_out(key), "secret": secret}


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyOut)
def revoke_api_key(key_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return api_key_out(ProductService(db).revoke_api_key(user=principal.user, key_id=key_id))


@router.post("/api-keys/{key_id}/touch", response_model=ApiKeyOut)
def touch_api_key(key_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return api_key_out(ProductService(db).touch_api_key(user=principal.user, key_id=key_id))


@router.get("/entitlements", response_model=EntitlementOut)
def entitlements(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return entitlement_out(ProductService(db).entitlement_snapshot(user=principal.user, org_id=org_id))


@router.get("/usage/rollups", response_model=list[UsageRollupOut])
def usage_rollups(org_id: str, period: str | None = None, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_member(principal.user.id, org_id)
    return [usage_rollup_out(rollup) for rollup in service.repo.list_usage_rollups(org_id=org_id, period=period)]


@router.post("/budget-alerts", response_model=BudgetAlertOut)
def create_budget_alert(payload: BudgetAlertCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return budget_alert_out(ProductService(db).create_budget_alert(user=principal.user, data=payload.model_dump()))


@router.get("/budget-alerts", response_model=list[BudgetAlertOut])
def list_budget_alerts(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_member(principal.user.id, org_id)
    return [budget_alert_out(alert) for alert in service.repo.list_budget_alerts(org_id=org_id)]


@router.patch("/enterprise/sso", response_model=SsoConfigOut)
def update_sso(payload: SsoConfigUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return sso_config_out(ProductService(db).update_sso_configuration(user=principal.user, data=payload.model_dump()))


@router.get("/enterprise/sso", response_model=SsoConfigOut | None)
def get_sso(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict | None:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    config = service.repo.get_sso_configuration(org_id=org_id)
    return sso_config_out(config) if config else None


@router.patch("/enterprise/scim", response_model=ScimConfigOut)
def update_scim(payload: ScimConfigUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return scim_config_out(ProductService(db).update_scim_configuration(user=principal.user, data=payload.model_dump()))


@router.get("/enterprise/scim", response_model=ScimConfigOut | None)
def get_scim(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict | None:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    config = service.repo.get_scim_configuration(org_id=org_id)
    return scim_config_out(config) if config else None


@router.post("/enterprise/scim/sync-events", response_model=ScimSyncOut)
def create_scim_sync(payload: ScimSyncCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return scim_sync_out(ProductService(db).create_scim_sync_event(user=principal.user, data=payload.model_dump()))


@router.get("/enterprise/scim/sync-events", response_model=list[ScimSyncOut])
def list_scim_sync(org_id: str, limit: int = Query(default=50, ge=1, le=100), principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    return [scim_sync_out(event) for event in service.repo.list_scim_sync_events(org_id=org_id, limit=limit)]


@router.get("/enterprise/audit", response_model=list[AdvancedAuditOut])
def advanced_audit(
    org_id: str,
    event_type: str = "",
    risk: str = "",
    actor_user_id: str = "",
    resource_type: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    principal: ProductPrincipal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    return [advanced_audit_out(record) for record in service.repo.search_advanced_audit_records(org_id=org_id, event_type=event_type, risk=risk, actor_user_id=actor_user_id, resource_type=resource_type, limit=limit)]


@router.get("/enterprise/security-dashboard", response_model=SecurityDashboardOut)
def security_dashboard(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return ProductService(db).security_dashboard(user=principal.user, org_id=org_id)


@router.post("/enterprise/security-policies", response_model=SecurityPolicyOut)
def create_security_policy(payload: SecurityPolicyCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return security_policy_out(ProductService(db).create_security_policy(user=principal.user, data=payload.model_dump()))


@router.get("/enterprise/security-policies", response_model=list[SecurityPolicyOut])
def list_security_policies(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    return [security_policy_out(policy) for policy in service.repo.list_security_policies(org_id=org_id)]


@router.post("/enterprise/compliance-exports", response_model=ComplianceExportOut)
def create_compliance_export(payload: ComplianceExportCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return compliance_export_out(ProductService(db).create_compliance_export(user=principal.user, data=payload.model_dump()))


@router.get("/enterprise/compliance-exports", response_model=list[ComplianceExportOut])
def list_compliance_exports(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    return [compliance_export_out(export) for export in service.repo.list_compliance_exports(org_id=org_id)]


@router.post("/enterprise/retention-rules", response_model=RetentionRuleOut)
def create_retention_rule(payload: RetentionRuleCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return retention_rule_out(ProductService(db).create_retention_rule(user=principal.user, data=payload.model_dump()))


@router.get("/enterprise/retention-rules", response_model=list[RetentionRuleOut])
def list_retention_rules(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> list[dict]:
    service = ProductService(db)
    service.require_org_role(principal.user.id, org_id, {"owner", "admin"})
    return [retention_rule_out(rule) for rule in service.repo.list_retention_rules(org_id=org_id)]


@router.get("/enterprise/admin-portal", response_model=AdminPortalOut)
def admin_portal(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return ProductService(db).admin_portal(user=principal.user, org_id=org_id)


@router.patch("/enterprise/governance/settings")
def update_governance_settings(payload: GovernanceSettingsUpdate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    settings = ProductService(db).update_governance_settings(user=principal.user, data=payload.model_dump())
    return {"org_id": settings.org_id, "settings": settings.settings_json, "v3_governance_ref": settings.v3_governance_ref}


@router.post("/enterprise/governance/workflows", response_model=GovernanceWorkflowOut)
def create_governance_workflow(payload: GovernanceWorkflowCreate, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return governance_workflow_out(ProductService(db).create_governance_workflow(user=principal.user, data=payload.model_dump()))


@router.get("/enterprise/governance-dashboard", response_model=GovernanceDashboardOut)
def governance_dashboard(org_id: str, principal: ProductPrincipal = Depends(current_principal), db: Session = Depends(get_db)) -> dict:
    return ProductService(db).governance_dashboard(user=principal.user, org_id=org_id)


@router.get("/audit-logs", response_model=list[AuditOut])
def audit_logs(
    org_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    principal: ProductPrincipal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [audit_out(event) for event in ProductRepository(db).list_audit_events(user_id=principal.user.id, org_id=org_id, limit=limit)]
