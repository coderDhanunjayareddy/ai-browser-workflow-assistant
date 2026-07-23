from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.product.dependencies import ProductPrincipal, current_principal
from app.product.repositories import ProductRepository
from app.product.schemas import (
    AuditOut,
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
    SavedTaskCreate,
    SavedTaskOut,
    SavedTaskUpdate,
    SettingsUpdate,
    TaskRunRequest,
    TeamCreate,
    TeamOut,
    TemplateCreate,
    TemplateForkRequest,
    TemplateOut,
    TemplateRunRequest,
    TemplateUpdate,
    TemplateVersionOut,
    TokenResponse,
    UserOut,
    WorkflowCreate,
    WorkflowOut,
    WorkspaceCreate,
    WorkspaceOut,
)
from app.product.serializers import (
    audit_out,
    notification_out,
    org_out,
    replay_share_out,
    resource_version_out,
    saved_task_out,
    team_out,
    template_out,
    template_version_out,
    user_out,
    workflow_out,
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


@router.get("/audit-logs", response_model=list[AuditOut])
def audit_logs(
    org_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    principal: ProductPrincipal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [audit_out(event) for event in ProductRepository(db).list_audit_events(user_id=principal.user.id, org_id=org_id, limit=limit)]
