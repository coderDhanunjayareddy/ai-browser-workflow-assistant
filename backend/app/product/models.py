from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


class V5User(Base):
    __tablename__ = "v5_users"

    id = Column(String, primary_key=True, default=new_id)
    email = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(Text, nullable=False)
    status = Column(String, default="active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    profile = relationship("V5UserProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences = relationship("V5UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    memberships = relationship("V5OrganizationMember", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("V5Session", back_populates="user", cascade="all, delete-orphan")


class V5UserProfile(Base):
    __tablename__ = "v5_user_profiles"

    user_id = Column(String, ForeignKey("v5_users.id", ondelete="CASCADE"), primary_key=True)
    avatar_url = Column(Text, default="")
    locale = Column(String, default="en-US", nullable=False)
    timezone = Column(String, default="UTC", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("V5User", back_populates="profile")


class V5UserPreference(Base):
    __tablename__ = "v5_user_preferences"

    user_id = Column(String, ForeignKey("v5_users.id", ondelete="CASCADE"), primary_key=True)
    preferences = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("V5User", back_populates="preferences")


class V5Organization(Base):
    __tablename__ = "v5_organizations"

    id = Column(String, primary_key=True, default=new_id)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, default="active", nullable=False)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    members = relationship("V5OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    teams = relationship("V5Team", back_populates="organization", cascade="all, delete-orphan")
    workspaces = relationship("V5Workspace", back_populates="organization", cascade="all, delete-orphan")
    settings = relationship("V5OrganizationSetting", back_populates="organization", uselist=False, cascade="all, delete-orphan")


class V5OrganizationMember(Base):
    __tablename__ = "v5_organization_members"
    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_v5_org_member"),)

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("v5_users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, default="member", nullable=False)
    status = Column(String, default="active", nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organization = relationship("V5Organization", back_populates="members")
    user = relationship("V5User", back_populates="memberships")


class V5Team(Base):
    __tablename__ = "v5_teams"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organization = relationship("V5Organization", back_populates="teams")
    members = relationship("V5TeamMember", back_populates="team", cascade="all, delete-orphan")


class V5TeamMember(Base):
    __tablename__ = "v5_team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_v5_team_member"),)

    id = Column(String, primary_key=True, default=new_id)
    team_id = Column(String, ForeignKey("v5_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("v5_users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, default="member", nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("V5Team", back_populates="members")


class V5Workspace(Base):
    __tablename__ = "v5_workspaces"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="active", nullable=False)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organization = relationship("V5Organization", back_populates="workspaces")
    members = relationship("V5WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    settings = relationship("V5WorkspaceSetting", back_populates="workspace", uselist=False, cascade="all, delete-orphan")
    workflow_runs = relationship("V5WorkflowRun", back_populates="workspace", cascade="all, delete-orphan")


class V5WorkspaceMember(Base):
    __tablename__ = "v5_workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_v5_workspace_member"),)

    id = Column(String, primary_key=True, default=new_id)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("v5_users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, default="member", nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    workspace = relationship("V5Workspace", back_populates="members")


class V5WorkflowRun(Base):
    __tablename__ = "v5_workflow_runs"

    id = Column(String, primary_key=True, default=new_id)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("v5_users.id"), nullable=False, index=True)
    title = Column(Text, default="")
    status = Column(String, default="running", nullable=False, index=True)
    input_summary = Column(Text, default="")
    output_summary = Column(Text, default="")
    error_class = Column(String, default="")
    runtime_ref = Column(String, default="")
    browser_session_ref = Column(String, default="")
    parameters_json = Column(JSON, default=dict, nullable=False)
    source_workflow_id = Column(String, ForeignKey("v5_workflow_runs.id"), nullable=True, index=True)
    rerun_of_workflow_id = Column(String, ForeignKey("v5_workflow_runs.id"), nullable=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    workspace = relationship("V5Workspace", back_populates="workflow_runs")
    steps = relationship("V5WorkflowStep", back_populates="workflow_run", cascade="all, delete-orphan")


class V5WorkflowStep(Base):
    __tablename__ = "v5_workflow_steps"

    id = Column(String, primary_key=True, default=new_id)
    workflow_run_id = Column(String, ForeignKey("v5_workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_index = Column(Integer, default=0, nullable=False)
    action_type = Column(String, default="")
    status = Column(String, default="pending", nullable=False)
    capability_id = Column(String, default="")
    validation_status = Column(String, default="")
    duration_ms = Column(Integer, default=0, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    workflow_run = relationship("V5WorkflowRun", back_populates="steps")


class V5Session(Base):
    __tablename__ = "v5_sessions"

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(String, ForeignKey("v5_users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(Text, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("V5User", back_populates="sessions")


class V5OrganizationSetting(Base):
    __tablename__ = "v5_organization_settings"

    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), primary_key=True)
    settings = Column(JSON, default=dict, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    organization = relationship("V5Organization", back_populates="settings")


class V5WorkspaceSetting(Base):
    __tablename__ = "v5_workspace_settings"

    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), primary_key=True)
    settings = Column(JSON, default=dict, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    workspace = relationship("V5Workspace", back_populates="settings")


class V5AuditEvent(Base):
    __tablename__ = "v5_audit_events"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_user_id = Column(String, ForeignKey("v5_users.id"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    resource_type = Column(String, default="", nullable=False)
    resource_id = Column(String, default="", nullable=False)
    risk_level = Column(String, default="low", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5ReplayShare(Base):
    __tablename__ = "v5_replay_shares"

    id = Column(String, primary_key=True, default=new_id)
    workflow_run_id = Column(String, ForeignKey("v5_workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False, index=True)
    share_token = Column(String, nullable=False, unique=True, index=True)
    visibility = Column(String, default="workspace", nullable=False)
    redaction_policy = Column(JSON, default=dict, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5SavedTask(Base):
    __tablename__ = "v5_saved_tasks"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    owner_user_id = Column(String, ForeignKey("v5_users.id"), nullable=False, index=True)
    scope = Column(String, default="personal", nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    input_prompt = Column(Text, default="")
    parameters_json = Column(JSON, default=dict, nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    favorite = Column(Boolean, default=False, nullable=False)
    source_workflow_id = Column(String, ForeignKey("v5_workflow_runs.id"), nullable=True, index=True)
    run_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5Template(Base):
    __tablename__ = "v5_templates"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    owner_user_id = Column(String, ForeignKey("v5_users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    parameter_schema = Column(JSON, default=dict, nullable=False)
    body = Column(JSON, default=dict, nullable=False)
    current_version = Column(Integer, default=1, nullable=False)
    forked_from_template_id = Column(String, ForeignKey("v5_templates.id"), nullable=True, index=True)
    status = Column(String, default="active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    versions = relationship("V5TemplateVersion", back_populates="template", cascade="all, delete-orphan")


class V5TemplateVersion(Base):
    __tablename__ = "v5_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "version_number", name="uq_v5_template_version"),)

    id = Column(String, primary_key=True, default=new_id)
    template_id = Column(String, ForeignKey("v5_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    parameter_schema = Column(JSON, default=dict, nullable=False)
    body = Column(JSON, default=dict, nullable=False)
    change_summary = Column(Text, default="")
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    template = relationship("V5Template", back_populates="versions")


class V5ResourceVersion(Base):
    __tablename__ = "v5_resource_versions"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    resource_type = Column(String, nullable=False, index=True)
    resource_id = Column(String, nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    snapshot_json = Column(JSON, default=dict, nullable=False)
    diff_metadata = Column(JSON, default=dict, nullable=False)
    change_summary = Column(Text, default="")
    rollback_of_version_id = Column(String, ForeignKey("v5_resource_versions.id"), nullable=True)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5Notification(Base):
    __tablename__ = "v5_notifications"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String, ForeignKey("v5_users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, default="")
    metadata_json = Column(JSON, default=dict, nullable=False)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5Invitation(Base):
    __tablename__ = "v5_invitations"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(String, ForeignKey("v5_teams.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    email = Column(String, nullable=False, index=True)
    role = Column(String, default="member", nullable=False)
    status = Column(String, default="pending", nullable=False, index=True)
    invited_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    accepted_at = Column(DateTime, nullable=True)


class V5TeamActivity(Base):
    __tablename__ = "v5_team_activity"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(String, ForeignKey("v5_teams.id", ondelete="CASCADE"), nullable=True, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_user_id = Column(String, ForeignKey("v5_users.id"), nullable=True, index=True)
    activity_type = Column(String, nullable=False, index=True)
    summary = Column(Text, default="")
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5WorkspaceShare(Base):
    __tablename__ = "v5_workspace_shares"
    __table_args__ = (UniqueConstraint("workspace_id", "team_id", name="uq_v5_workspace_team_share"),)

    id = Column(String, primary_key=True, default=new_id)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id = Column(String, ForeignKey("v5_teams.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, default="member", nullable=False)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5Assistant(Base):
    __tablename__ = "v5_assistants"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id = Column(String, ForeignKey("v5_users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    instructions = Column(Text, default="")
    capability_permissions = Column(JSON, default=list, nullable=False)
    status = Column(String, default="draft", nullable=False, index=True)
    current_version = Column(Integer, default=1, nullable=False)
    metrics_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    versions = relationship("V5AssistantVersion", back_populates="assistant", cascade="all, delete-orphan")


class V5AssistantVersion(Base):
    __tablename__ = "v5_assistant_versions"
    __table_args__ = (UniqueConstraint("assistant_id", "version_number", name="uq_v5_assistant_version"),)

    id = Column(String, primary_key=True, default=new_id)
    assistant_id = Column(String, ForeignKey("v5_assistants.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    instructions = Column(Text, default="")
    capability_permissions = Column(JSON, default=list, nullable=False)
    change_summary = Column(Text, default="")
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    assistant = relationship("V5Assistant", back_populates="versions")


class V5AssistantWorkspaceAssignment(Base):
    __tablename__ = "v5_assistant_workspace_assignments"
    __table_args__ = (UniqueConstraint("assistant_id", "workspace_id", name="uq_v5_assistant_workspace"),)

    id = Column(String, primary_key=True, default=new_id)
    assistant_id = Column(String, ForeignKey("v5_assistants.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, default="assistant", nullable=False)
    assigned_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5IntegrationCatalogItem(Base):
    __tablename__ = "v5_integration_catalog"

    id = Column(String, primary_key=True, default=new_id)
    provider_key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="productivity", nullable=False)
    auth_type = Column(String, default="oauth_stub", nullable=False)
    scopes = Column(JSON, default=list, nullable=False)
    capabilities = Column(JSON, default=list, nullable=False)
    status = Column(String, default="available", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5IntegrationConnection(Base):
    __tablename__ = "v5_integration_connections"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    provider_key = Column(String, nullable=False, index=True)
    connected_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    status = Column(String, default="connected", nullable=False, index=True)
    token_ref = Column(String, default="", nullable=False)
    token_metadata = Column(JSON, default=dict, nullable=False)
    health_status = Column(String, default="unknown", nullable=False)
    last_health_check_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5IntegrationHealthEvent(Base):
    __tablename__ = "v5_integration_health_events"

    id = Column(String, primary_key=True, default=new_id)
    connection_id = Column(String, ForeignKey("v5_integration_connections.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String, nullable=False)
    latency_ms = Column(Integer, default=0, nullable=False)
    message = Column(Text, default="")
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5UsageRecord(Base):
    __tablename__ = "v5_usage_records"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id = Column(String, ForeignKey("v5_users.id"), nullable=True, index=True)
    workflow_run_id = Column(String, ForeignKey("v5_workflow_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    usage_type = Column(String, nullable=False, index=True)
    quantity = Column(Integer, default=0, nullable=False)
    unit = Column(String, default="count", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5BillingPlan(Base):
    __tablename__ = "v5_billing_plans"

    id = Column(String, primary_key=True, default=new_id)
    plan_key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    tier = Column(String, nullable=False, index=True)
    monthly_price_cents = Column(Integer, default=0, nullable=False)
    seat_price_cents = Column(Integer, default=0, nullable=False)
    included_usage = Column(JSON, default=dict, nullable=False)
    limits_json = Column(JSON, default=dict, nullable=False)
    entitlements_json = Column(JSON, default=dict, nullable=False)
    billing_model = Column(String, default="flat", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5Subscription(Base):
    __tablename__ = "v5_subscriptions"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    plan_key = Column(String, nullable=False, index=True)
    status = Column(String, default="trialing", nullable=False, index=True)
    seat_count = Column(Integer, default=1, nullable=False)
    trial_ends_at = Column(DateTime, nullable=True)
    current_period_start = Column(DateTime, default=datetime.utcnow, nullable=False)
    current_period_end = Column(DateTime, nullable=True)
    provider = Column(String, default="stub", nullable=False)
    provider_ref = Column(String, default="", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5Invoice(Base):
    __tablename__ = "v5_invoices"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(String, ForeignKey("v5_subscriptions.id", ondelete="CASCADE"), nullable=True, index=True)
    invoice_number = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, default="draft", nullable=False)
    amount_due_cents = Column(Integer, default=0, nullable=False)
    currency = Column(String, default="USD", nullable=False)
    line_items = Column(JSON, default=list, nullable=False)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    paid_at = Column(DateTime, nullable=True)


class V5BillingEvent(Base):
    __tablename__ = "v5_billing_events"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    resource_type = Column(String, default="", nullable=False)
    resource_id = Column(String, default="", nullable=False)
    provider = Column(String, default="stub", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5BillingSetting(Base):
    __tablename__ = "v5_billing_settings"

    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), primary_key=True)
    billing_email = Column(String, default="", nullable=False)
    tax_metadata = Column(JSON, default=dict, nullable=False)
    provider_customer_ref = Column(String, default="", nullable=False)
    payment_provider = Column(String, default="stub", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5ApiKey(Base):
    __tablename__ = "v5_api_keys"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    key_hash = Column(Text, nullable=False, unique=True)
    key_preview = Column(String, nullable=False)
    scopes = Column(JSON, default=list, nullable=False)
    status = Column(String, default="active", nullable=False, index=True)
    usage_count = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    rotated_from_key_id = Column(String, ForeignKey("v5_api_keys.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class V5EntitlementSnapshot(Base):
    __tablename__ = "v5_entitlement_snapshots"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_key = Column(String, nullable=False, index=True)
    features_json = Column(JSON, default=dict, nullable=False)
    limits_json = Column(JSON, default=dict, nullable=False)
    usage_json = Column(JSON, default=dict, nullable=False)
    enforcement_metadata = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5UsageRollup(Base):
    __tablename__ = "v5_usage_rollups"
    __table_args__ = (UniqueConstraint("org_id", "period", "usage_type", "workspace_id", name="uq_v5_usage_rollup"),)

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    period = Column(String, nullable=False, index=True)
    usage_type = Column(String, nullable=False, index=True)
    quantity = Column(Integer, default=0, nullable=False)
    unit = Column(String, default="count", nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5BudgetAlert(Base):
    __tablename__ = "v5_budget_alerts"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False)
    monthly_budget_cents = Column(Integer, default=0, nullable=False)
    threshold_percent = Column(Integer, default=80, nullable=False)
    status = Column(String, default="active", nullable=False, index=True)
    last_triggered_at = Column(DateTime, nullable=True)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5SsoConfiguration(Base):
    __tablename__ = "v5_sso_configurations"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    saml_metadata = Column(JSON, default=dict, nullable=False)
    oidc_metadata = Column(JSON, default=dict, nullable=False)
    idp_metadata = Column(JSON, default=dict, nullable=False)
    login_policy = Column(JSON, default=dict, nullable=False)
    domain_verification = Column(JSON, default=dict, nullable=False)
    enforce_sso = Column(Boolean, default=False, nullable=False)
    provider_mode = Column(String, default="stub", nullable=False)
    status = Column(String, default="draft", nullable=False, index=True)
    updated_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5ScimConfiguration(Base):
    __tablename__ = "v5_scim_configurations"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    base_url = Column(Text, default="", nullable=False)
    bearer_token_hash = Column(Text, default="", nullable=False)
    user_mapping = Column(JSON, default=dict, nullable=False)
    group_mapping = Column(JSON, default=dict, nullable=False)
    provisioning_status = Column(String, default="disabled", nullable=False, index=True)
    metadata_json = Column(JSON, default=dict, nullable=False)
    updated_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5ScimSyncEvent(Base):
    __tablename__ = "v5_scim_sync_events"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    scim_config_id = Column(String, ForeignKey("v5_scim_configurations.id", ondelete="CASCADE"), nullable=True, index=True)
    resource_type = Column(String, default="user", nullable=False, index=True)
    external_id = Column(String, default="", nullable=False)
    status = Column(String, default="stubbed", nullable=False)
    action = Column(String, default="sync", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5AdvancedAuditRecord(Base):
    __tablename__ = "v5_advanced_audit_records"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    source_audit_event_id = Column(String, ForeignKey("v5_audit_events.id"), nullable=True, index=True)
    actor_user_id = Column(String, ForeignKey("v5_users.id"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    resource_type = Column(String, default="", nullable=False, index=True)
    resource_id = Column(String, default="", nullable=False, index=True)
    risk_classification = Column(String, default="low", nullable=False, index=True)
    retention_until = Column(DateTime, nullable=True)
    immutable_hash = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5SecurityPolicy(Base):
    __tablename__ = "v5_security_policies"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    policy_type = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    rules_json = Column(JSON, default=dict, nullable=False)
    status = Column(String, default="active", nullable=False, index=True)
    current_version = Column(Integer, default=1, nullable=False)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5SecurityPolicyVersion(Base):
    __tablename__ = "v5_security_policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "version_number", name="uq_v5_security_policy_version"),)

    id = Column(String, primary_key=True, default=new_id)
    policy_id = Column(String, ForeignKey("v5_security_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    rules_json = Column(JSON, default=dict, nullable=False)
    change_summary = Column(Text, default="")
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5ComplianceExport(Base):
    __tablename__ = "v5_compliance_exports"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    export_type = Column(String, nullable=False, index=True)
    status = Column(String, default="queued", nullable=False, index=True)
    filters_json = Column(JSON, default=dict, nullable=False)
    artifact_ref = Column(String, default="", nullable=False)
    requested_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    retention_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)


class V5RetentionRule(Base):
    __tablename__ = "v5_retention_rules"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    data_type = Column(String, nullable=False, index=True)
    retention_days = Column(Integer, default=365, nullable=False)
    action = Column(String, default="retain", nullable=False)
    status = Column(String, default="active", nullable=False, index=True)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5RetentionJob(Base):
    __tablename__ = "v5_retention_jobs"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String, ForeignKey("v5_retention_rules.id", ondelete="CASCADE"), nullable=True, index=True)
    status = Column(String, default="scheduled", nullable=False, index=True)
    scheduled_for = Column(DateTime, default=datetime.utcnow, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5AdminDiagnostic(Base):
    __tablename__ = "v5_admin_diagnostics"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    diagnostic_type = Column(String, nullable=False, index=True)
    status = Column(String, default="ok", nullable=False)
    summary = Column(Text, default="")
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class V5GovernanceSetting(Base):
    __tablename__ = "v5_governance_settings"

    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), primary_key=True)
    settings_json = Column(JSON, default=dict, nullable=False)
    v3_governance_ref = Column(String, default="v3-governance", nullable=False)
    updated_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class V5GovernanceApprovalWorkflow(Base):
    __tablename__ = "v5_governance_approval_workflows"

    id = Column(String, primary_key=True, default=new_id)
    org_id = Column(String, ForeignKey("v5_organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(String, ForeignKey("v5_workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String, nullable=False)
    trigger_policy = Column(JSON, default=dict, nullable=False)
    approver_rules = Column(JSON, default=dict, nullable=False)
    status = Column(String, default="active", nullable=False, index=True)
    created_by = Column(String, ForeignKey("v5_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
