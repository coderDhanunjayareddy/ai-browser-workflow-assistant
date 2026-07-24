from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str | None = None


class TeamCreate(BaseModel):
    name: str = Field(min_length=1)


class TeamMemberAdd(BaseModel):
    user_id: str
    role: str = "member"


class InvitationCreate(BaseModel):
    org_id: str
    email: str = Field(min_length=3)
    role: str = "member"
    team_id: str | None = None
    workspace_id: str | None = None


class WorkspaceShareCreate(BaseModel):
    team_id: str
    role: str = "member"


class WorkspaceCreate(BaseModel):
    org_id: str
    name: str = Field(min_length=1)
    description: str = ""


class WorkflowCreate(BaseModel):
    workspace_id: str
    title: str = ""
    status: str = "running"
    input_summary: str = ""
    output_summary: str = ""
    runtime_ref: str = ""
    browser_session_ref: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class SettingsUpdate(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class ReplayShareCreate(BaseModel):
    visibility: str = "workspace"
    redaction_policy: dict[str, Any] = Field(default_factory=lambda: {"secrets": True, "credentials": True})


class SavedTaskCreate(BaseModel):
    workspace_id: str | None = None
    org_id: str | None = None
    scope: str = "personal"
    title: str = Field(min_length=1)
    description: str = ""
    input_prompt: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False
    source_workflow_id: str | None = None


class SavedTaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    input_prompt: str | None = None
    scope: str | None = None
    parameters: dict[str, Any] | None = None
    tags: list[str] | None = None
    favorite: bool | None = None


class TaskRunRequest(BaseModel):
    workspace_id: str | None = None


class TemplateCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=1)
    description: str = ""
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    body: dict[str, Any] = Field(default_factory=dict)


class TemplateUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    parameter_schema: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    change_summary: str = ""


class TemplateRunRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


class TemplateForkRequest(BaseModel):
    workspace_id: str | None = None


class ResourceVersionCreate(BaseModel):
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    org_id: str | None = None
    workspace_id: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)
    change_summary: str = ""
    rollback_of_version_id: str | None = None


class AssistantCreate(BaseModel):
    org_id: str
    name: str = Field(min_length=1)
    description: str = ""
    instructions: str = ""
    capability_permissions: list[str] = Field(default_factory=list)


class AssistantUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    capability_permissions: list[str] | None = None
    change_summary: str = ""


class AssistantAssignRequest(BaseModel):
    workspace_id: str
    role: str = "assistant"


class IntegrationConnectRequest(BaseModel):
    org_id: str
    provider_key: str
    workspace_id: str | None = None
    token_metadata: dict[str, Any] = Field(default_factory=dict)


class IntegrationHealthRequest(BaseModel):
    status: str = "healthy"
    latency_ms: int = 0
    message: str = ""


class UsageRecordCreate(BaseModel):
    org_id: str
    workspace_id: str | None = None
    workflow_run_id: str | None = None
    usage_type: str
    quantity: int = 0
    unit: str = "count"
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    status: str
    preferences: dict[str, Any] = Field(default_factory=dict)


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    role: str | None = None


class TeamOut(BaseModel):
    id: str
    org_id: str
    name: str
    created_at: datetime


class TeamMemberOut(BaseModel):
    id: str
    team_id: str
    user_id: str
    role: str
    joined_at: datetime


class InvitationOut(BaseModel):
    id: str
    org_id: str
    team_id: str | None
    workspace_id: str | None
    email: str
    role: str
    status: str
    token: str
    created_at: datetime


class TeamActivityOut(BaseModel):
    id: str
    org_id: str
    team_id: str | None
    workspace_id: str | None
    actor_user_id: str | None
    activity_type: str
    summary: str
    metadata: dict[str, Any]
    created_at: datetime


class WorkspaceShareOut(BaseModel):
    id: str
    workspace_id: str
    org_id: str
    team_id: str
    role: str
    created_at: datetime


class WorkspaceOut(BaseModel):
    id: str
    org_id: str
    name: str
    description: str
    role: str | None = None
    status: str
    created_at: datetime


class WorkflowOut(BaseModel):
    id: str
    workspace_id: str
    org_id: str
    title: str
    status: str
    input_summary: str
    output_summary: str
    runtime_ref: str
    browser_session_ref: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    steps: list[dict[str, Any]] = Field(default_factory=list)


class AuditOut(BaseModel):
    id: str
    org_id: str | None
    workspace_id: str | None
    actor_user_id: str | None
    event_type: str
    resource_type: str
    resource_id: str
    risk_level: str
    metadata: dict[str, Any]
    created_at: datetime


class ReplayOut(BaseModel):
    workflow: dict[str, Any]
    timeline: list[dict[str, Any]]
    metadata: dict[str, Any]


class ReplayShareOut(BaseModel):
    id: str
    workflow_run_id: str
    share_token: str
    visibility: str
    redaction_policy: dict[str, Any]
    created_at: datetime


class SavedTaskOut(BaseModel):
    id: str
    org_id: str | None
    workspace_id: str | None
    scope: str
    title: str
    description: str
    input_prompt: str
    parameters: dict[str, Any]
    tags: list[str]
    favorite: bool
    run_count: int
    created_at: datetime
    updated_at: datetime


class TemplateOut(BaseModel):
    id: str
    org_id: str
    workspace_id: str | None
    title: str
    description: str
    parameter_schema: dict[str, Any]
    body: dict[str, Any]
    current_version: int
    forked_from_template_id: str | None
    created_at: datetime
    updated_at: datetime


class TemplateVersionOut(BaseModel):
    id: str
    template_id: str
    version_number: int
    title: str
    change_summary: str
    created_at: datetime


class ResourceVersionOut(BaseModel):
    id: str
    org_id: str | None
    workspace_id: str | None
    resource_type: str
    resource_id: str
    version_number: int
    snapshot: dict[str, Any]
    diff: dict[str, Any]
    change_summary: str
    rollback_of_version_id: str | None
    created_at: datetime


class NotificationOut(BaseModel):
    id: str
    org_id: str | None
    workspace_id: str | None
    event_type: str
    title: str
    body: str
    metadata: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class AssistantOut(BaseModel):
    id: str
    org_id: str
    name: str
    description: str
    instructions: str
    capability_permissions: list[str]
    status: str
    current_version: int
    metrics: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AssistantVersionOut(BaseModel):
    id: str
    assistant_id: str
    version_number: int
    name: str
    change_summary: str
    created_at: datetime


class AssistantAssignmentOut(BaseModel):
    id: str
    assistant_id: str
    workspace_id: str
    org_id: str
    role: str
    created_at: datetime


class IntegrationCatalogOut(BaseModel):
    id: str
    provider_key: str
    name: str
    category: str
    auth_type: str
    scopes: list[str]
    capabilities: list[str]
    status: str


class IntegrationConnectionOut(BaseModel):
    id: str
    org_id: str
    workspace_id: str | None
    provider_key: str
    status: str
    token_metadata: dict[str, Any]
    health_status: str
    last_health_check_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IntegrationHealthOut(BaseModel):
    id: str
    connection_id: str
    status: str
    latency_ms: int
    message: str
    created_at: datetime


class AnalyticsOut(BaseModel):
    org_id: str
    workflow_status: dict[str, int]
    success_rate: float
    capability_usage: dict[str, int]
    workspace_workflows: dict[str, int]
    team_activity_count: int
    trend: list[dict[str, Any]]
    export: dict[str, Any]


class UsageDashboardOut(BaseModel):
    org_id: str
    totals: dict[str, int]
    by_workspace: dict[str, dict[str, int]]
    by_user: dict[str, dict[str, int]]
    records: list[dict[str, Any]]
