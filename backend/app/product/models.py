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
