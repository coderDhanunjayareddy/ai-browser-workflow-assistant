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
