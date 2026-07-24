from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.product import models


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> models.V5User | None:
        return self.db.scalar(select(models.V5User).where(models.V5User.email == email.lower()))

    def get_user(self, user_id: str) -> models.V5User | None:
        return self.db.get(models.V5User, user_id)

    def create_user(self, *, email: str, name: str, password_hash: str) -> models.V5User:
        user = models.V5User(email=email.lower(), name=name, password_hash=password_hash)
        self.db.add(user)
        self.db.flush()
        self.db.add(models.V5UserProfile(user_id=user.id))
        self.db.add(models.V5UserPreference(user_id=user.id, preferences={"theme": "system", "notifications": True}))
        return user

    def create_session(self, *, user_id: str, token_hash: str, expires_at: datetime) -> models.V5Session:
        session = models.V5Session(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(session)
        self.db.flush()
        return session

    def get_session(self, session_id: str) -> models.V5Session | None:
        return self.db.get(models.V5Session, session_id)

    def get_session_by_hash(self, token_hash: str) -> models.V5Session | None:
        return self.db.scalar(select(models.V5Session).where(models.V5Session.token_hash == token_hash))

    def create_org(self, *, name: str, slug: str, user_id: str) -> models.V5Organization:
        org = models.V5Organization(name=name, slug=slug, created_by=user_id)
        self.db.add(org)
        self.db.flush()
        self.db.add(models.V5OrganizationMember(org_id=org.id, user_id=user_id, role="owner"))
        self.db.add(models.V5OrganizationSetting(org_id=org.id, settings={"retention_days": 30, "default_workspace_role": "member"}))
        return org

    def list_user_orgs(self, user_id: str) -> list[models.V5Organization]:
        stmt = (
            select(models.V5Organization)
            .join(models.V5OrganizationMember)
            .where(models.V5OrganizationMember.user_id == user_id, models.V5OrganizationMember.status == "active")
            .order_by(models.V5Organization.created_at.desc())
        )
        return list(self.db.scalars(stmt))

    def org_role(self, org_id: str, user_id: str) -> str | None:
        member = self.db.scalar(select(models.V5OrganizationMember).where(
            models.V5OrganizationMember.org_id == org_id,
            models.V5OrganizationMember.user_id == user_id,
            models.V5OrganizationMember.status == "active",
        ))
        return member.role if member else None

    def create_team(self, *, org_id: str, user_id: str, name: str) -> models.V5Team:
        team = models.V5Team(org_id=org_id, name=name, created_by=user_id)
        self.db.add(team)
        self.db.flush()
        self.db.add(models.V5TeamMember(team_id=team.id, user_id=user_id, role="owner"))
        return team

    def get_team(self, team_id: str) -> models.V5Team | None:
        return self.db.get(models.V5Team, team_id)

    def list_teams(self, org_id: str) -> list[models.V5Team]:
        return list(self.db.scalars(select(models.V5Team).where(models.V5Team.org_id == org_id).order_by(models.V5Team.created_at.desc())))

    def add_team_member(self, *, team_id: str, user_id: str, role: str) -> models.V5TeamMember:
        member = self.db.scalar(select(models.V5TeamMember).where(models.V5TeamMember.team_id == team_id, models.V5TeamMember.user_id == user_id))
        if member:
            member.role = role
            return member
        member = models.V5TeamMember(team_id=team_id, user_id=user_id, role=role)
        self.db.add(member)
        self.db.flush()
        return member

    def list_team_members(self, team_id: str) -> list[models.V5TeamMember]:
        return list(self.db.scalars(select(models.V5TeamMember).where(models.V5TeamMember.team_id == team_id).order_by(models.V5TeamMember.joined_at.desc())))

    def create_invitation(self, *, org_id: str, invited_by: str, email: str, role: str, team_id: str | None = None, workspace_id: str | None = None) -> models.V5Invitation:
        invitation = models.V5Invitation(org_id=org_id, team_id=team_id, workspace_id=workspace_id, invited_by=invited_by, email=email.lower(), role=role, token=models.new_id())
        self.db.add(invitation)
        self.db.flush()
        return invitation

    def list_invitations(self, *, org_id: str) -> list[models.V5Invitation]:
        return list(self.db.scalars(select(models.V5Invitation).where(models.V5Invitation.org_id == org_id).order_by(models.V5Invitation.created_at.desc())))

    def add_team_activity(self, *, org_id: str, activity_type: str, summary: str, actor_user_id: str | None = None, team_id: str | None = None, workspace_id: str | None = None, metadata: dict[str, Any] | None = None) -> models.V5TeamActivity:
        activity = models.V5TeamActivity(org_id=org_id, team_id=team_id, workspace_id=workspace_id, actor_user_id=actor_user_id, activity_type=activity_type, summary=summary, metadata_json=metadata or {})
        self.db.add(activity)
        self.db.flush()
        return activity

    def list_team_activity(self, *, org_id: str, team_id: str | None = None, limit: int = 50) -> list[models.V5TeamActivity]:
        stmt = select(models.V5TeamActivity).where(models.V5TeamActivity.org_id == org_id)
        if team_id:
            stmt = stmt.where(models.V5TeamActivity.team_id == team_id)
        return list(self.db.scalars(stmt.order_by(models.V5TeamActivity.created_at.desc()).limit(max(1, min(limit, 100)))))

    def share_workspace_with_team(self, *, workspace: models.V5Workspace, team_id: str, role: str, user_id: str) -> models.V5WorkspaceShare:
        share = self.db.scalar(select(models.V5WorkspaceShare).where(models.V5WorkspaceShare.workspace_id == workspace.id, models.V5WorkspaceShare.team_id == team_id))
        if share:
            share.role = role
            return share
        share = models.V5WorkspaceShare(workspace_id=workspace.id, org_id=workspace.org_id, team_id=team_id, role=role, created_by=user_id)
        self.db.add(share)
        self.db.flush()
        return share

    def create_workspace(self, *, org_id: str, user_id: str, name: str, description: str = "") -> models.V5Workspace:
        workspace = models.V5Workspace(org_id=org_id, name=name, description=description, created_by=user_id)
        self.db.add(workspace)
        self.db.flush()
        self.db.add(models.V5WorkspaceMember(workspace_id=workspace.id, user_id=user_id, role="owner"))
        self.db.add(models.V5WorkspaceSetting(workspace_id=workspace.id, settings={"retention_days": 30, "workflow_visibility": "workspace"}))
        return workspace

    def list_workspaces(self, *, user_id: str, org_id: str | None = None) -> list[models.V5Workspace]:
        stmt = (
            select(models.V5Workspace)
            .join(models.V5WorkspaceMember)
            .where(models.V5WorkspaceMember.user_id == user_id, models.V5Workspace.status == "active")
        )
        if org_id:
            stmt = stmt.where(models.V5Workspace.org_id == org_id)
        return list(self.db.scalars(stmt.order_by(models.V5Workspace.created_at.desc())))

    def workspace_role(self, workspace_id: str, user_id: str) -> str | None:
        member = self.db.scalar(select(models.V5WorkspaceMember).where(
            models.V5WorkspaceMember.workspace_id == workspace_id,
            models.V5WorkspaceMember.user_id == user_id,
        ))
        return member.role if member else None

    def get_workspace(self, workspace_id: str) -> models.V5Workspace | None:
        return self.db.get(models.V5Workspace, workspace_id)

    def create_workflow_run(self, *, workspace: models.V5Workspace, user_id: str, data: dict[str, Any]) -> models.V5WorkflowRun:
        run = models.V5WorkflowRun(
            workspace_id=workspace.id,
            org_id=workspace.org_id,
            user_id=user_id,
            title=str(data.get("title") or data.get("input_summary") or "Untitled workflow"),
            status=str(data.get("status") or "running"),
            input_summary=str(data.get("input_summary") or ""),
            output_summary=str(data.get("output_summary") or ""),
            runtime_ref=str(data.get("runtime_ref") or ""),
            browser_session_ref=str(data.get("browser_session_ref") or ""),
            parameters_json=dict(data.get("parameters") or data.get("parameters_json") or {}),
            source_workflow_id=data.get("source_workflow_id") or None,
            rerun_of_workflow_id=data.get("rerun_of_workflow_id") or None,
        )
        self.db.add(run)
        self.db.flush()
        for index, step in enumerate(data.get("steps") or []):
            if isinstance(step, dict):
                self.db.add(models.V5WorkflowStep(
                    workflow_run_id=run.id,
                    step_index=int(step.get("step_index", index)),
                    action_type=str(step.get("action_type") or ""),
                    status=str(step.get("status") or "completed"),
                    capability_id=str(step.get("capability_id") or ""),
                    validation_status=str(step.get("validation_status") or ""),
                    duration_ms=int(step.get("duration_ms") or 0),
                    metadata_json=dict(step.get("metadata") or {}),
                ))
        return run

    def list_workflow_runs(self, *, user_id: str, workspace_id: str | None = None, limit: int = 50) -> list[models.V5WorkflowRun]:
        stmt = select(models.V5WorkflowRun).join(models.V5WorkspaceMember, models.V5WorkspaceMember.workspace_id == models.V5WorkflowRun.workspace_id).where(
            models.V5WorkspaceMember.user_id == user_id
        )
        if workspace_id:
            stmt = stmt.where(models.V5WorkflowRun.workspace_id == workspace_id)
        return list(self.db.scalars(stmt.order_by(models.V5WorkflowRun.created_at.desc()).limit(max(1, min(limit, 100)))))

    def get_workflow_run_for_user(self, run_id: str, user_id: str) -> models.V5WorkflowRun | None:
        stmt = select(models.V5WorkflowRun).join(models.V5WorkspaceMember, models.V5WorkspaceMember.workspace_id == models.V5WorkflowRun.workspace_id).where(
            models.V5WorkflowRun.id == run_id,
            models.V5WorkspaceMember.user_id == user_id,
        )
        return self.db.scalar(stmt)

    def clone_workflow_run(self, *, source: models.V5WorkflowRun, user_id: str, rerun: bool) -> models.V5WorkflowRun:
        run = models.V5WorkflowRun(
            workspace_id=source.workspace_id,
            org_id=source.org_id,
            user_id=user_id,
            title=f"{source.title or 'Untitled workflow'} {'rerun' if rerun else 'copy'}",
            status="queued" if rerun else source.status,
            input_summary=source.input_summary,
            output_summary="" if rerun else source.output_summary,
            runtime_ref=source.runtime_ref,
            browser_session_ref=source.browser_session_ref,
            parameters_json=dict(source.parameters_json or {}),
            source_workflow_id=source.id,
            rerun_of_workflow_id=source.id if rerun else None,
        )
        self.db.add(run)
        self.db.flush()
        for step in sorted(source.steps, key=lambda item: item.step_index):
            self.db.add(models.V5WorkflowStep(
                workflow_run_id=run.id,
                step_index=step.step_index,
                action_type=step.action_type,
                status="pending" if rerun else step.status,
                capability_id=step.capability_id,
                validation_status="" if rerun else step.validation_status,
                duration_ms=0 if rerun else step.duration_ms,
                metadata_json=dict(step.metadata_json or {}),
            ))
        return run

    def create_replay_share(self, *, run: models.V5WorkflowRun, user_id: str, visibility: str, redaction_policy: dict[str, Any], expires_at: datetime | None = None) -> models.V5ReplayShare:
        share = models.V5ReplayShare(
            workflow_run_id=run.id,
            org_id=run.org_id,
            workspace_id=run.workspace_id,
            created_by=user_id,
            share_token=models.new_id(),
            visibility=visibility,
            redaction_policy=redaction_policy,
            expires_at=expires_at,
        )
        self.db.add(share)
        self.db.flush()
        return share

    def create_saved_task(self, *, user_id: str, data: dict[str, Any], workspace: models.V5Workspace | None = None) -> models.V5SavedTask:
        task = models.V5SavedTask(
            org_id=workspace.org_id if workspace else data.get("org_id"),
            workspace_id=workspace.id if workspace else data.get("workspace_id"),
            owner_user_id=user_id,
            scope=str(data.get("scope") or ("workspace" if workspace else "personal")),
            title=str(data.get("title") or "Untitled task"),
            description=str(data.get("description") or ""),
            input_prompt=str(data.get("input_prompt") or ""),
            parameters_json=dict(data.get("parameters") or {}),
            tags=list(data.get("tags") or []),
            favorite=bool(data.get("favorite") or False),
            source_workflow_id=data.get("source_workflow_id") or None,
        )
        self.db.add(task)
        self.db.flush()
        return task

    def list_saved_tasks(self, *, user_id: str, workspace_ids: list[str], query: str = "", tag: str = "", limit: int = 50) -> list[models.V5SavedTask]:
        stmt = select(models.V5SavedTask).where(or_(
            models.V5SavedTask.owner_user_id == user_id,
            models.V5SavedTask.workspace_id.in_(workspace_ids or [""]),
        ))
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(or_(models.V5SavedTask.title.ilike(like), models.V5SavedTask.description.ilike(like), models.V5SavedTask.input_prompt.ilike(like)))
        items = list(self.db.scalars(stmt.order_by(models.V5SavedTask.favorite.desc(), models.V5SavedTask.updated_at.desc()).limit(max(1, min(limit, 100)))))
        if tag:
            items = [item for item in items if tag in (item.tags or [])]
        return items

    def get_saved_task(self, task_id: str) -> models.V5SavedTask | None:
        return self.db.get(models.V5SavedTask, task_id)

    def create_template(self, *, user_id: str, workspace: models.V5Workspace, data: dict[str, Any], forked_from_template_id: str | None = None) -> models.V5Template:
        template = models.V5Template(
            org_id=workspace.org_id,
            workspace_id=workspace.id,
            owner_user_id=user_id,
            title=str(data.get("title") or "Untitled template"),
            description=str(data.get("description") or ""),
            parameter_schema=dict(data.get("parameter_schema") or {}),
            body=dict(data.get("body") or {}),
            forked_from_template_id=forked_from_template_id,
        )
        self.db.add(template)
        self.db.flush()
        self.add_template_version(template=template, user_id=user_id, change_summary="Initial version")
        return template

    def add_template_version(self, *, template: models.V5Template, user_id: str, change_summary: str = "") -> models.V5TemplateVersion:
        version = models.V5TemplateVersion(
            template_id=template.id,
            version_number=template.current_version,
            title=template.title,
            description=template.description,
            parameter_schema=dict(template.parameter_schema or {}),
            body=dict(template.body or {}),
            change_summary=change_summary,
            created_by=user_id,
        )
        self.db.add(version)
        return version

    def list_templates(self, *, workspace_ids: list[str], query: str = "", limit: int = 50) -> list[models.V5Template]:
        stmt = select(models.V5Template).where(models.V5Template.workspace_id.in_(workspace_ids or [""]), models.V5Template.status == "active")
        if query:
            like = f"%{query.lower()}%"
            stmt = stmt.where(or_(models.V5Template.title.ilike(like), models.V5Template.description.ilike(like)))
        return list(self.db.scalars(stmt.order_by(models.V5Template.updated_at.desc()).limit(max(1, min(limit, 100)))))

    def get_template(self, template_id: str) -> models.V5Template | None:
        return self.db.get(models.V5Template, template_id)

    def create_resource_version(self, *, user_id: str, resource_type: str, resource_id: str, org_id: str | None, workspace_id: str | None, snapshot: dict[str, Any], change_summary: str = "", rollback_of_version_id: str | None = None) -> models.V5ResourceVersion:
        latest = self.db.scalar(select(models.V5ResourceVersion).where(
            models.V5ResourceVersion.resource_type == resource_type,
            models.V5ResourceVersion.resource_id == resource_id,
        ).order_by(models.V5ResourceVersion.version_number.desc()))
        previous = dict(latest.snapshot_json or {}) if latest else {}
        version = models.V5ResourceVersion(
            org_id=org_id,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            version_number=(latest.version_number + 1) if latest else 1,
            snapshot_json=snapshot,
            diff_metadata=_diff(previous, snapshot),
            change_summary=change_summary,
            rollback_of_version_id=rollback_of_version_id,
            created_by=user_id,
        )
        self.db.add(version)
        self.db.flush()
        return version

    def list_resource_versions(self, *, resource_type: str, resource_id: str) -> list[models.V5ResourceVersion]:
        stmt = select(models.V5ResourceVersion).where(
            models.V5ResourceVersion.resource_type == resource_type,
            models.V5ResourceVersion.resource_id == resource_id,
        ).order_by(models.V5ResourceVersion.version_number.desc())
        return list(self.db.scalars(stmt))

    def get_resource_version(self, version_id: str) -> models.V5ResourceVersion | None:
        return self.db.get(models.V5ResourceVersion, version_id)

    def create_notification(self, *, user_id: str, event_type: str, title: str, body: str = "", org_id: str | None = None, workspace_id: str | None = None, metadata: dict[str, Any] | None = None) -> models.V5Notification:
        notification = models.V5Notification(
            user_id=user_id,
            org_id=org_id,
            workspace_id=workspace_id,
            event_type=event_type,
            title=title,
            body=body,
            metadata_json=metadata or {},
        )
        self.db.add(notification)
        self.db.flush()
        return notification

    def list_notifications(self, *, user_id: str, unread_only: bool = False, limit: int = 50) -> list[models.V5Notification]:
        stmt = select(models.V5Notification).where(models.V5Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(models.V5Notification.read_at.is_(None))
        return list(self.db.scalars(stmt.order_by(models.V5Notification.created_at.desc()).limit(max(1, min(limit, 100)))))

    def get_notification(self, notification_id: str) -> models.V5Notification | None:
        return self.db.get(models.V5Notification, notification_id)

    def create_assistant(self, *, user_id: str, org_id: str, data: dict[str, Any]) -> models.V5Assistant:
        assistant = models.V5Assistant(
            org_id=org_id,
            owner_user_id=user_id,
            name=str(data.get("name") or "Untitled assistant"),
            description=str(data.get("description") or ""),
            instructions=str(data.get("instructions") or ""),
            capability_permissions=list(data.get("capability_permissions") or []),
            metrics_json={"runs": 0, "successes": 0, "failures": 0},
        )
        self.db.add(assistant)
        self.db.flush()
        self.add_assistant_version(assistant=assistant, user_id=user_id, change_summary="Initial version")
        return assistant

    def add_assistant_version(self, *, assistant: models.V5Assistant, user_id: str, change_summary: str = "") -> models.V5AssistantVersion:
        version = models.V5AssistantVersion(
            assistant_id=assistant.id,
            version_number=assistant.current_version,
            name=assistant.name,
            description=assistant.description,
            instructions=assistant.instructions,
            capability_permissions=list(assistant.capability_permissions or []),
            change_summary=change_summary,
            created_by=user_id,
        )
        self.db.add(version)
        return version

    def get_assistant(self, assistant_id: str) -> models.V5Assistant | None:
        return self.db.get(models.V5Assistant, assistant_id)

    def list_assistants(self, *, org_ids: list[str], limit: int = 50) -> list[models.V5Assistant]:
        return list(self.db.scalars(select(models.V5Assistant).where(models.V5Assistant.org_id.in_(org_ids or [""])).order_by(models.V5Assistant.updated_at.desc()).limit(max(1, min(limit, 100)))))

    def assign_assistant(self, *, assistant: models.V5Assistant, workspace: models.V5Workspace, user_id: str, role: str = "assistant") -> models.V5AssistantWorkspaceAssignment:
        assignment = self.db.scalar(select(models.V5AssistantWorkspaceAssignment).where(
            models.V5AssistantWorkspaceAssignment.assistant_id == assistant.id,
            models.V5AssistantWorkspaceAssignment.workspace_id == workspace.id,
        ))
        if assignment:
            assignment.role = role
            return assignment
        assignment = models.V5AssistantWorkspaceAssignment(assistant_id=assistant.id, workspace_id=workspace.id, org_id=workspace.org_id, assigned_by=user_id, role=role)
        self.db.add(assignment)
        self.db.flush()
        return assignment

    def ensure_integration_catalog(self) -> list[models.V5IntegrationCatalogItem]:
        defaults = [
            ("github", "GitHub", "development", ["repo", "workflow"], ["issues", "pull_requests"]),
            ("google_workspace", "Google Workspace", "productivity", ["drive", "docs"], ["files", "docs"]),
            ("slack", "Slack", "communication", ["channels", "messages"], ["notifications", "messages"]),
            ("jira", "Jira", "project_management", ["issues"], ["tickets", "boards"]),
        ]
        for provider_key, name, category, scopes, capabilities in defaults:
            if not self.db.scalar(select(models.V5IntegrationCatalogItem).where(models.V5IntegrationCatalogItem.provider_key == provider_key)):
                self.db.add(models.V5IntegrationCatalogItem(provider_key=provider_key, name=name, category=category, scopes=scopes, capabilities=capabilities))
        self.db.flush()
        return list(self.db.scalars(select(models.V5IntegrationCatalogItem).order_by(models.V5IntegrationCatalogItem.name.asc())))

    def create_integration_connection(self, *, user_id: str, org_id: str, provider_key: str, workspace_id: str | None = None, token_metadata: dict[str, Any] | None = None) -> models.V5IntegrationConnection:
        connection = models.V5IntegrationConnection(org_id=org_id, workspace_id=workspace_id, provider_key=provider_key, connected_by=user_id, token_ref=f"stub:{models.new_id()}", token_metadata=token_metadata or {"mode": "oauth_stub"}, health_status="unknown")
        self.db.add(connection)
        self.db.flush()
        return connection

    def list_integration_connections(self, *, org_ids: list[str]) -> list[models.V5IntegrationConnection]:
        return list(self.db.scalars(select(models.V5IntegrationConnection).where(models.V5IntegrationConnection.org_id.in_(org_ids or [""])).order_by(models.V5IntegrationConnection.updated_at.desc())))

    def get_integration_connection(self, connection_id: str) -> models.V5IntegrationConnection | None:
        return self.db.get(models.V5IntegrationConnection, connection_id)

    def record_integration_health(self, *, connection: models.V5IntegrationConnection, status_value: str, latency_ms: int = 0, message: str = "") -> models.V5IntegrationHealthEvent:
        connection.health_status = status_value
        connection.last_health_check_at = datetime.utcnow()
        connection.updated_at = datetime.utcnow()
        event = models.V5IntegrationHealthEvent(connection_id=connection.id, status=status_value, latency_ms=latency_ms, message=message)
        self.db.add(event)
        self.db.flush()
        return event

    def create_usage_record(self, *, org_id: str, usage_type: str, quantity: int, unit: str = "count", workspace_id: str | None = None, user_id: str | None = None, workflow_run_id: str | None = None, metadata: dict[str, Any] | None = None) -> models.V5UsageRecord:
        record = models.V5UsageRecord(org_id=org_id, workspace_id=workspace_id, user_id=user_id, workflow_run_id=workflow_run_id, usage_type=usage_type, quantity=quantity, unit=unit, metadata_json=metadata or {})
        self.db.add(record)
        self.db.flush()
        return record

    def list_usage_records(self, *, org_id: str) -> list[models.V5UsageRecord]:
        return list(self.db.scalars(select(models.V5UsageRecord).where(models.V5UsageRecord.org_id == org_id).order_by(models.V5UsageRecord.created_at.desc())))

    def workflow_status_counts(self, *, org_id: str) -> dict[str, int]:
        rows = self.db.execute(select(models.V5WorkflowRun.status, func.count(models.V5WorkflowRun.id)).where(models.V5WorkflowRun.org_id == org_id).group_by(models.V5WorkflowRun.status)).all()
        return {str(status): int(count) for status, count in rows}

    def capability_usage_counts(self, *, org_id: str) -> dict[str, int]:
        rows = self.db.execute(select(models.V5WorkflowStep.capability_id, func.count(models.V5WorkflowStep.id)).join(models.V5WorkflowRun).where(models.V5WorkflowRun.org_id == org_id).group_by(models.V5WorkflowStep.capability_id)).all()
        return {str(capability or "unknown"): int(count) for capability, count in rows}

    def workspace_workflow_counts(self, *, org_id: str) -> dict[str, int]:
        rows = self.db.execute(select(models.V5WorkflowRun.workspace_id, func.count(models.V5WorkflowRun.id)).where(models.V5WorkflowRun.org_id == org_id).group_by(models.V5WorkflowRun.workspace_id)).all()
        return {str(workspace_id): int(count) for workspace_id, count in rows}

    def write_audit(self, *, event_type: str, actor_user_id: str | None = None, org_id: str | None = None, workspace_id: str | None = None, resource_type: str = "", resource_id: str = "", risk_level: str = "low", metadata: dict[str, Any] | None = None) -> models.V5AuditEvent:
        event = models.V5AuditEvent(
            event_type=event_type,
            actor_user_id=actor_user_id,
            org_id=org_id,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            risk_level=risk_level,
            metadata_json=metadata or {},
        )
        self.db.add(event)
        return event

    def list_audit_events(self, *, user_id: str, org_id: str, limit: int = 50) -> list[models.V5AuditEvent]:
        if self.org_role(org_id, user_id) not in {"owner", "admin"}:
            return []
        stmt = select(models.V5AuditEvent).where(models.V5AuditEvent.org_id == org_id).order_by(models.V5AuditEvent.created_at.desc()).limit(max(1, min(limit, 100)))
        return list(self.db.scalars(stmt))


def _diff(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    keys = set(previous) | set(current)
    return {
        "added": sorted(key for key in keys if key not in previous),
        "removed": sorted(key for key in keys if key not in current),
        "changed": sorted(key for key in keys if key in previous and key in current and previous[key] != current[key]),
    }
