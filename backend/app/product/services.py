from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.product import models, security
from app.product.repositories import ProductRepository


ADMIN_ROLES = {"owner", "admin"}
WORKSPACE_WRITE_ROLES = {"owner", "admin", "member"}


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def register(self, *, email: str, password: str, name: str) -> tuple[models.V5User, str]:
        if self.repo.get_user_by_email(email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
        user = self.repo.create_user(email=email, name=name, password_hash=security.hash_password(password))
        self.repo.write_audit(event_type="user.registered", actor_user_id=user.id, resource_type="user", resource_id=user.id)
        token = self._issue_token(user)
        self.db.commit()
        return user, token

    def login(self, *, email: str, password: str) -> tuple[models.V5User, str]:
        user = self.repo.get_user_by_email(email)
        if not user or not security.verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
        token = self._issue_token(user)
        self.repo.write_audit(event_type="auth.login", actor_user_id=user.id, resource_type="user", resource_id=user.id)
        self.db.commit()
        return user, token

    def logout(self, *, session_id: str, user_id: str) -> None:
        session = self.repo.get_session(session_id)
        if session and session.user_id == user_id:
            session.revoked = True
            self.repo.write_audit(event_type="auth.logout", actor_user_id=user_id, resource_type="session", resource_id=session_id)
            self.db.commit()

    def create_org(self, *, user: models.V5User, name: str, slug: str | None = None) -> models.V5Organization:
        org = self.repo.create_org(name=name, slug=_slug(slug or name), user_id=user.id)
        self.repo.write_audit(event_type="org.created", actor_user_id=user.id, org_id=org.id, resource_type="organization", resource_id=org.id)
        self.db.commit()
        return org

    def create_team(self, *, user: models.V5User, org_id: str, name: str) -> models.V5Team:
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        team = self.repo.create_team(org_id=org_id, user_id=user.id, name=name)
        self.repo.add_team_activity(org_id=org_id, team_id=team.id, actor_user_id=user.id, activity_type="team.created", summary=f"Team {team.name} created")
        self.repo.write_audit(event_type="team.created", actor_user_id=user.id, org_id=org_id, resource_type="team", resource_id=team.id)
        self.db.commit()
        return team

    def add_team_member(self, *, user: models.V5User, team_id: str, member_user_id: str, role: str) -> models.V5TeamMember:
        team = self.require_team_admin(user.id, team_id)
        if not self.repo.get_user(member_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
        self.require_org_member(member_user_id, team.org_id)
        member = self.repo.add_team_member(team_id=team.id, user_id=member_user_id, role=role)
        self.repo.add_team_activity(org_id=team.org_id, team_id=team.id, actor_user_id=user.id, activity_type="team.member.added", summary=f"Member added as {role}", metadata={"user_id": member_user_id})
        self.repo.write_audit(event_type="team.member.added", actor_user_id=user.id, org_id=team.org_id, resource_type="team_member", resource_id=member.id)
        self.db.commit()
        return member

    def invite_user(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5Invitation:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        workspace_id = data.get("workspace_id")
        team_id = data.get("team_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin"})
            if workspace.org_id != org_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace does not belong to org")
        if team_id:
            team = self.repo.get_team(str(team_id))
            if not team or team.org_id != org_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
        invitation = self.repo.create_invitation(org_id=org_id, invited_by=user.id, email=str(data["email"]), role=str(data.get("role") or "member"), team_id=team_id, workspace_id=workspace_id)
        self.repo.add_team_activity(org_id=org_id, team_id=team_id, workspace_id=workspace_id, actor_user_id=user.id, activity_type="invitation.created", summary=f"Invitation sent to {invitation.email}")
        self.repo.write_audit(event_type="invitation.created", actor_user_id=user.id, org_id=org_id, workspace_id=workspace_id, resource_type="invitation", resource_id=invitation.id)
        self.db.commit()
        return invitation

    def share_workspace(self, *, user: models.V5User, workspace_id: str, team_id: str, role: str) -> models.V5WorkspaceShare:
        workspace = self.require_workspace_role(user.id, workspace_id, {"owner", "admin"})
        team = self.repo.get_team(team_id)
        if not team or team.org_id != workspace.org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
        share = self.repo.share_workspace_with_team(workspace=workspace, team_id=team.id, role=role, user_id=user.id)
        self.repo.add_team_activity(org_id=workspace.org_id, team_id=team.id, workspace_id=workspace.id, actor_user_id=user.id, activity_type="workspace.shared", summary=f"Workspace shared with {team.name} as {role}")
        self.repo.write_audit(event_type="workspace.shared", actor_user_id=user.id, org_id=workspace.org_id, workspace_id=workspace.id, resource_type="workspace_share", resource_id=share.id)
        self.db.commit()
        return share

    def create_workspace(self, *, user: models.V5User, org_id: str, name: str, description: str = "") -> models.V5Workspace:
        self.require_org_member(user.id, org_id)
        workspace = self.repo.create_workspace(org_id=org_id, user_id=user.id, name=name, description=description)
        self.repo.write_audit(event_type="workspace.created", actor_user_id=user.id, org_id=org_id, workspace_id=workspace.id, resource_type="workspace", resource_id=workspace.id)
        self.db.commit()
        return workspace

    def create_workflow_run(self, *, user: models.V5User, workspace_id: str, data: dict[str, Any]) -> models.V5WorkflowRun:
        workspace = self.require_workspace_role(user.id, workspace_id, WORKSPACE_WRITE_ROLES)
        run = self.repo.create_workflow_run(workspace=workspace, user_id=user.id, data=data)
        self.repo.write_audit(event_type="workflow.created", actor_user_id=user.id, org_id=workspace.org_id, workspace_id=workspace.id, resource_type="workflow", resource_id=run.id)
        if run.status in {"completed", "failed"}:
            self.repo.create_notification(
                user_id=user.id,
                org_id=workspace.org_id,
                workspace_id=workspace.id,
                event_type=f"workflow.{run.status}",
                title=f"Workflow {run.status}",
                body=run.title,
                metadata={"workflow_id": run.id},
            )
        self.db.commit()
        return run

    def clone_workflow_run(self, *, user: models.V5User, workflow_id: str, rerun: bool) -> models.V5WorkflowRun:
        source = self.repo.get_workflow_run_for_user(workflow_id, user.id)
        if not source:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
        self.require_workspace_role(user.id, source.workspace_id, WORKSPACE_WRITE_ROLES)
        run = self.repo.clone_workflow_run(source=source, user_id=user.id, rerun=rerun)
        event = "workflow.rerun.created" if rerun else "workflow.cloned"
        self.repo.write_audit(event_type=event, actor_user_id=user.id, org_id=run.org_id, workspace_id=run.workspace_id, resource_type="workflow", resource_id=run.id, metadata={"source_workflow_id": source.id})
        if rerun:
            self.repo.create_notification(user_id=user.id, org_id=run.org_id, workspace_id=run.workspace_id, event_type="workflow.rerun.queued", title="Workflow rerun queued", body=run.title, metadata={"workflow_id": run.id, "source_workflow_id": source.id})
        self.db.commit()
        return run

    def replay_for_workflow(self, *, user: models.V5User, workflow_id: str) -> dict[str, Any]:
        run = self.repo.get_workflow_run_for_user(workflow_id, user.id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
        timeline = []
        for step in sorted(run.steps, key=lambda item: item.step_index):
            metadata = dict(step.metadata_json or {})
            timeline.append({
                "step_id": step.id,
                "step_index": step.step_index,
                "action_type": step.action_type,
                "status": step.status,
                "duration_ms": step.duration_ms,
                "validation": {"status": step.validation_status, **dict(metadata.get("validation") or {})},
                "governance": dict(metadata.get("governance") or {}),
                "visual_region": metadata.get("visual_region"),
                "screenshot_ref": metadata.get("screenshot_ref"),
                "metadata": _redact_metadata(metadata),
            })
        return {
            "workflow": {"id": run.id, "title": run.title, "status": run.status, "runtime_ref": run.runtime_ref, "browser_session_ref": run.browser_session_ref},
            "timeline": timeline,
            "metadata": {"step_count": len(timeline), "redaction": "basic", "shareable": True},
        }

    def create_replay_share(self, *, user: models.V5User, workflow_id: str, visibility: str, redaction_policy: dict[str, Any]) -> models.V5ReplayShare:
        run = self.repo.get_workflow_run_for_user(workflow_id, user.id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workflow not found")
        self.require_workspace_role(user.id, run.workspace_id, {"owner", "admin", "member", "viewer"})
        share = self.repo.create_replay_share(run=run, user_id=user.id, visibility=visibility, redaction_policy=redaction_policy)
        self.repo.write_audit(event_type="replay.share.created", actor_user_id=user.id, org_id=run.org_id, workspace_id=run.workspace_id, resource_type="replay_share", resource_id=share.id, metadata={"workflow_id": run.id, "visibility": visibility})
        self.db.commit()
        return share

    def create_saved_task(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5SavedTask:
        workspace = None
        if data.get("workspace_id"):
            workspace = self.require_workspace_role(user.id, str(data["workspace_id"]), WORKSPACE_WRITE_ROLES)
        task = self.repo.create_saved_task(user_id=user.id, data=data, workspace=workspace)
        self.repo.write_audit(event_type="task.saved", actor_user_id=user.id, org_id=task.org_id, workspace_id=task.workspace_id, resource_type="saved_task", resource_id=task.id)
        self.db.commit()
        return task

    def update_saved_task(self, *, user: models.V5User, task_id: str, data: dict[str, Any]) -> models.V5SavedTask:
        task = self.require_task_access(user.id, task_id, write=True)
        for field in ["title", "description", "input_prompt", "scope"]:
            if field in data:
                setattr(task, field, str(data[field]))
        if "parameters" in data:
            task.parameters_json = dict(data["parameters"] or {})
        if "tags" in data:
            task.tags = list(data["tags"] or [])
        if "favorite" in data:
            task.favorite = bool(data["favorite"])
        task.updated_at = datetime.utcnow()
        self.repo.write_audit(event_type="task.updated", actor_user_id=user.id, org_id=task.org_id, workspace_id=task.workspace_id, resource_type="saved_task", resource_id=task.id)
        self.db.commit()
        return task

    def run_saved_task(self, *, user: models.V5User, task_id: str, workspace_id: str | None = None) -> models.V5WorkflowRun:
        task = self.require_task_access(user.id, task_id, write=False)
        target_workspace_id = workspace_id or task.workspace_id
        if not target_workspace_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace_id required")
        workspace = self.require_workspace_role(user.id, target_workspace_id, WORKSPACE_WRITE_ROLES)
        task.run_count += 1
        task.updated_at = datetime.utcnow()
        run = self.repo.create_workflow_run(workspace=workspace, user_id=user.id, data={
            "title": task.title,
            "input_summary": task.input_prompt,
            "status": "queued",
            "parameters": task.parameters_json or {},
        })
        self.repo.write_audit(event_type="task.run.created", actor_user_id=user.id, org_id=workspace.org_id, workspace_id=workspace.id, resource_type="workflow", resource_id=run.id, metadata={"saved_task_id": task.id})
        self.db.commit()
        return run

    def create_template(self, *, user: models.V5User, workspace_id: str, data: dict[str, Any]) -> models.V5Template:
        workspace = self.require_workspace_role(user.id, workspace_id, WORKSPACE_WRITE_ROLES)
        template = self.repo.create_template(user_id=user.id, workspace=workspace, data=data)
        self.repo.create_resource_version(user_id=user.id, resource_type="template", resource_id=template.id, org_id=template.org_id, workspace_id=template.workspace_id, snapshot=template_snapshot(template), change_summary="Initial template")
        self.repo.write_audit(event_type="template.created", actor_user_id=user.id, org_id=template.org_id, workspace_id=template.workspace_id, resource_type="template", resource_id=template.id)
        self.db.commit()
        return template

    def update_template(self, *, user: models.V5User, template_id: str, data: dict[str, Any]) -> models.V5Template:
        template = self.require_template_access(user.id, template_id, write=True)
        for field in ["title", "description"]:
            if field in data:
                setattr(template, field, str(data[field]))
        if "parameter_schema" in data:
            template.parameter_schema = dict(data["parameter_schema"] or {})
        if "body" in data:
            template.body = dict(data["body"] or {})
        template.current_version += 1
        template.updated_at = datetime.utcnow()
        self.repo.add_template_version(template=template, user_id=user.id, change_summary=str(data.get("change_summary") or "Template updated"))
        self.repo.create_resource_version(user_id=user.id, resource_type="template", resource_id=template.id, org_id=template.org_id, workspace_id=template.workspace_id, snapshot=template_snapshot(template), change_summary=str(data.get("change_summary") or "Template updated"))
        self.repo.write_audit(event_type="template.updated", actor_user_id=user.id, org_id=template.org_id, workspace_id=template.workspace_id, resource_type="template", resource_id=template.id)
        self.db.commit()
        return template

    def run_template(self, *, user: models.V5User, template_id: str, parameters: dict[str, Any]) -> models.V5WorkflowRun:
        template = self.require_template_access(user.id, template_id, write=False)
        workspace = self.require_workspace_role(user.id, template.workspace_id, WORKSPACE_WRITE_ROLES)
        run = self.repo.create_workflow_run(workspace=workspace, user_id=user.id, data={
            "title": template.title,
            "input_summary": str((template.body or {}).get("prompt") or template.description),
            "status": "queued",
            "parameters": parameters,
        })
        self.repo.write_audit(event_type="template.run.created", actor_user_id=user.id, org_id=template.org_id, workspace_id=template.workspace_id, resource_type="workflow", resource_id=run.id, metadata={"template_id": template.id})
        self.db.commit()
        return run

    def fork_template(self, *, user: models.V5User, template_id: str, workspace_id: str | None = None) -> models.V5Template:
        source = self.require_template_access(user.id, template_id, write=False)
        workspace = self.require_workspace_role(user.id, workspace_id or source.workspace_id, WORKSPACE_WRITE_ROLES)
        template = self.repo.create_template(user_id=user.id, workspace=workspace, data=template_snapshot(source), forked_from_template_id=source.id)
        self.repo.write_audit(event_type="template.forked", actor_user_id=user.id, org_id=template.org_id, workspace_id=template.workspace_id, resource_type="template", resource_id=template.id, metadata={"source_template_id": source.id})
        self.db.commit()
        return template

    def create_resource_version(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5ResourceVersion:
        workspace_id = data.get("workspace_id")
        org_id = data.get("org_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), WORKSPACE_WRITE_ROLES)
            org_id = workspace.org_id
        elif org_id:
            self.require_org_member(user.id, str(org_id))
        version = self.repo.create_resource_version(user_id=user.id, resource_type=str(data["resource_type"]), resource_id=str(data["resource_id"]), org_id=org_id, workspace_id=workspace_id, snapshot=dict(data.get("snapshot") or {}), change_summary=str(data.get("change_summary") or ""), rollback_of_version_id=data.get("rollback_of_version_id"))
        self.repo.write_audit(event_type="version.created", actor_user_id=user.id, org_id=version.org_id, workspace_id=version.workspace_id, resource_type="resource_version", resource_id=version.id)
        self.db.commit()
        return version

    def create_assistant(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5Assistant:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        assistant = self.repo.create_assistant(user_id=user.id, org_id=org_id, data=data)
        self.repo.write_audit(event_type="assistant.created", actor_user_id=user.id, org_id=org_id, resource_type="assistant", resource_id=assistant.id)
        self.db.commit()
        return assistant

    def update_assistant(self, *, user: models.V5User, assistant_id: str, data: dict[str, Any]) -> models.V5Assistant:
        assistant = self.require_assistant_access(user.id, assistant_id, write=True)
        for field in ["name", "description", "instructions"]:
            if field in data:
                setattr(assistant, field, str(data[field]))
        if "capability_permissions" in data:
            assistant.capability_permissions = list(data["capability_permissions"] or [])
        assistant.current_version += 1
        assistant.updated_at = datetime.utcnow()
        self.repo.add_assistant_version(assistant=assistant, user_id=user.id, change_summary=str(data.get("change_summary") or "Assistant updated"))
        self.repo.write_audit(event_type="assistant.updated", actor_user_id=user.id, org_id=assistant.org_id, resource_type="assistant", resource_id=assistant.id)
        self.db.commit()
        return assistant

    def set_assistant_status(self, *, user: models.V5User, assistant_id: str, status_value: str) -> models.V5Assistant:
        assistant = self.require_assistant_access(user.id, assistant_id, write=True)
        assistant.status = status_value
        assistant.updated_at = datetime.utcnow()
        self.repo.write_audit(event_type=f"assistant.{status_value}", actor_user_id=user.id, org_id=assistant.org_id, resource_type="assistant", resource_id=assistant.id)
        self.db.commit()
        return assistant

    def assign_assistant(self, *, user: models.V5User, assistant_id: str, workspace_id: str, role: str) -> models.V5AssistantWorkspaceAssignment:
        assistant = self.require_assistant_access(user.id, assistant_id, write=False)
        workspace = self.require_workspace_role(user.id, workspace_id, {"owner", "admin"})
        if workspace.org_id != assistant.org_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="workspace does not belong to assistant org")
        assignment = self.repo.assign_assistant(assistant=assistant, workspace=workspace, user_id=user.id, role=role)
        self.repo.write_audit(event_type="assistant.assigned", actor_user_id=user.id, org_id=assistant.org_id, workspace_id=workspace.id, resource_type="assistant_assignment", resource_id=assignment.id)
        self.db.commit()
        return assignment

    def connect_integration(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5IntegrationConnection:
        org_id = str(data["org_id"])
        workspace_id = data.get("workspace_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin"})
            org_id = workspace.org_id
        else:
            self.require_org_role(user.id, org_id, ADMIN_ROLES)
        self.repo.ensure_integration_catalog()
        connection = self.repo.create_integration_connection(user_id=user.id, org_id=org_id, workspace_id=workspace_id, provider_key=str(data["provider_key"]), token_metadata=dict(data.get("token_metadata") or {}))
        self.repo.write_audit(event_type="integration.connected", actor_user_id=user.id, org_id=org_id, workspace_id=workspace_id, resource_type="integration_connection", resource_id=connection.id, metadata={"provider_key": connection.provider_key})
        self.db.commit()
        return connection

    def record_integration_health(self, *, user: models.V5User, connection_id: str, status_value: str, latency_ms: int, message: str) -> models.V5IntegrationHealthEvent:
        connection = self.require_integration_access(user.id, connection_id, write=True)
        event = self.repo.record_integration_health(connection=connection, status_value=status_value, latency_ms=latency_ms, message=message)
        self.repo.write_audit(event_type="integration.health.checked", actor_user_id=user.id, org_id=connection.org_id, workspace_id=connection.workspace_id, resource_type="integration_connection", resource_id=connection.id)
        self.db.commit()
        return event

    def create_usage_record(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5UsageRecord:
        org_id = str(data["org_id"])
        workspace_id = data.get("workspace_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin", "member"})
            org_id = workspace.org_id
        else:
            self.require_org_member(user.id, org_id)
        record = self.repo.create_usage_record(org_id=org_id, workspace_id=workspace_id, user_id=user.id, workflow_run_id=data.get("workflow_run_id"), usage_type=str(data["usage_type"]), quantity=int(data.get("quantity") or 0), unit=str(data.get("unit") or "count"), metadata=dict(data.get("metadata") or {}))
        self.repo.upsert_usage_rollup(org_id=org_id, workspace_id=workspace_id, period=datetime.utcnow().strftime("%Y-%m"), usage_type=record.usage_type, quantity=record.quantity, unit=record.unit)
        self.db.commit()
        return record

    def create_subscription(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5Subscription:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        self.repo.ensure_billing_plans()
        plan = self.repo.get_plan(str(data.get("plan_key") or "free"))
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        trial_ends_at = datetime.utcnow() + timedelta(days=14) if data.get("trial") else None
        subscription = self.repo.upsert_subscription(org_id=org_id, plan_key=plan.plan_key, seat_count=max(1, int(data.get("seat_count") or 1)), status_value="trialing" if trial_ends_at else "active", trial_ends_at=trial_ends_at)
        self.repo.create_billing_event(org_id=org_id, event_type="subscription.updated", resource_type="subscription", resource_id=subscription.id, metadata={"plan_key": plan.plan_key})
        self.repo.write_audit(event_type="billing.subscription.updated", actor_user_id=user.id, org_id=org_id, resource_type="subscription", resource_id=subscription.id)
        self.db.commit()
        return subscription

    def update_billing_settings(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5BillingSetting:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        settings = self.repo.update_billing_settings(org_id=org_id, billing_email=str(data.get("billing_email") or ""), tax_metadata=dict(data.get("tax_metadata") or {}))
        self.repo.create_billing_event(org_id=org_id, event_type="billing.settings.updated", resource_type="billing_settings", resource_id=org_id)
        self.db.commit()
        return settings

    def create_invoice(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5Invoice:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        subscription = self.repo.get_subscription(org_id)
        invoice = self.repo.create_invoice(org_id=org_id, subscription_id=subscription.id if subscription else None, amount_due_cents=int(data.get("amount_due_cents") or 0), line_items=list(data.get("line_items") or []))
        self.repo.create_billing_event(org_id=org_id, event_type="invoice.created", resource_type="invoice", resource_id=invoice.id)
        self.db.commit()
        return invoice

    def create_api_key(self, *, user: models.V5User, data: dict[str, Any]) -> tuple[models.V5ApiKey, str]:
        org_id = str(data["org_id"])
        workspace_id = data.get("workspace_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin"})
            org_id = workspace.org_id
        else:
            self.require_org_role(user.id, org_id, ADMIN_ROLES)
        secret, key_hash, preview = security.create_api_key()
        key = self.repo.create_api_key(org_id=org_id, workspace_id=workspace_id, user_id=user.id, name=str(data["name"]), key_hash=key_hash, key_preview=preview, scopes=list(data.get("scopes") or []))
        self.repo.write_audit(event_type="api_key.created", actor_user_id=user.id, org_id=org_id, workspace_id=workspace_id, resource_type="api_key", resource_id=key.id)
        self.db.commit()
        return key, secret

    def rotate_api_key(self, *, user: models.V5User, key_id: str) -> tuple[models.V5ApiKey, str]:
        old = self.require_api_key_access(user.id, key_id, write=True)
        old.status = "rotated"
        old.revoked_at = datetime.utcnow()
        secret, key_hash, preview = security.create_api_key()
        key = self.repo.create_api_key(org_id=old.org_id, workspace_id=old.workspace_id, user_id=user.id, name=f"{old.name} rotated", key_hash=key_hash, key_preview=preview, scopes=list(old.scopes or []), rotated_from_key_id=old.id)
        self.repo.write_audit(event_type="api_key.rotated", actor_user_id=user.id, org_id=old.org_id, workspace_id=old.workspace_id, resource_type="api_key", resource_id=key.id)
        self.db.commit()
        return key, secret

    def revoke_api_key(self, *, user: models.V5User, key_id: str) -> models.V5ApiKey:
        key = self.require_api_key_access(user.id, key_id, write=True)
        key.status = "revoked"
        key.revoked_at = datetime.utcnow()
        self.repo.write_audit(event_type="api_key.revoked", actor_user_id=user.id, org_id=key.org_id, workspace_id=key.workspace_id, resource_type="api_key", resource_id=key.id)
        self.db.commit()
        return key

    def touch_api_key(self, *, user: models.V5User, key_id: str) -> models.V5ApiKey:
        key = self.require_api_key_access(user.id, key_id, write=False)
        self.repo.touch_api_key_usage(key=key)
        self.repo.upsert_usage_rollup(org_id=key.org_id, workspace_id=key.workspace_id, period=datetime.utcnow().strftime("%Y-%m"), usage_type="api_usage", quantity=1, unit="request")
        self.db.commit()
        return key

    def entitlement_snapshot(self, *, user: models.V5User, org_id: str) -> models.V5EntitlementSnapshot:
        self.require_org_member(user.id, org_id)
        self.repo.ensure_billing_plans()
        subscription = self.repo.get_subscription(org_id)
        plan = self.repo.get_plan(subscription.plan_key if subscription else "free")
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plan not found")
        usage = self.usage_dashboard(user=user, org_id=org_id)["totals"]
        snapshot = self.repo.create_entitlement_snapshot(org_id=org_id, plan=plan, usage=usage)
        self.db.commit()
        return snapshot

    def create_budget_alert(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5BudgetAlert:
        org_id = str(data["org_id"])
        workspace_id = data.get("workspace_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin"})
            org_id = workspace.org_id
        else:
            self.require_org_role(user.id, org_id, ADMIN_ROLES)
        alert = self.repo.create_budget_alert(org_id=org_id, workspace_id=workspace_id, user_id=user.id, name=str(data["name"]), monthly_budget_cents=int(data.get("monthly_budget_cents") or 0), threshold_percent=int(data.get("threshold_percent") or 80))
        self.repo.create_notification(user_id=user.id, org_id=org_id, workspace_id=workspace_id, event_type="budget_alert.created", title="Budget alert created", body=alert.name, metadata={"budget_alert_id": alert.id})
        self.repo.write_audit(event_type="budget_alert.created", actor_user_id=user.id, org_id=org_id, workspace_id=workspace_id, resource_type="budget_alert", resource_id=alert.id)
        self.db.commit()
        return alert

    def update_sso_configuration(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5SsoConfiguration:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        config = self.repo.upsert_sso_configuration(org_id=org_id, user_id=user.id, data=data)
        self.repo.create_advanced_audit_record(org_id=org_id, actor_user_id=user.id, event_type="sso.configuration.updated", resource_type="sso_configuration", resource_id=config.id, risk_classification="medium", metadata={"enforce_sso": config.enforce_sso})
        self.repo.write_audit(event_type="sso.configuration.updated", actor_user_id=user.id, org_id=org_id, resource_type="sso_configuration", resource_id=config.id, risk_level="medium")
        self.db.commit()
        return config

    def update_scim_configuration(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5ScimConfiguration:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        token_hash = security.token_hash(str(data.get("bearer_token") or "")) if data.get("bearer_token") else ""
        config = self.repo.upsert_scim_configuration(org_id=org_id, user_id=user.id, data=data, token_hash=token_hash)
        self.repo.create_advanced_audit_record(org_id=org_id, actor_user_id=user.id, event_type="scim.configuration.updated", resource_type="scim_configuration", resource_id=config.id, risk_classification="medium")
        self.db.commit()
        return config

    def create_scim_sync_event(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5ScimSyncEvent:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        config = self.repo.get_scim_configuration(org_id=org_id)
        event = self.repo.create_scim_sync_event(org_id=org_id, config_id=config.id if config else None, data=data)
        self.repo.create_advanced_audit_record(org_id=org_id, actor_user_id=user.id, event_type="scim.sync.stubbed", resource_type=event.resource_type, resource_id=event.external_id, risk_classification="low", metadata={"action": event.action})
        self.db.commit()
        return event

    def create_security_policy(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5SecurityPolicy:
        org_id = str(data["org_id"])
        workspace_id = data.get("workspace_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin"})
            org_id = workspace.org_id
        else:
            self.require_org_role(user.id, org_id, ADMIN_ROLES)
        policy = self.repo.create_security_policy(org_id=org_id, user_id=user.id, workspace_id=workspace_id, data=data)
        self.repo.create_advanced_audit_record(org_id=org_id, workspace_id=workspace_id, actor_user_id=user.id, event_type="security.policy.created", resource_type="security_policy", resource_id=policy.id, risk_classification="medium", metadata={"policy_type": policy.policy_type})
        self.db.commit()
        return policy

    def create_compliance_export(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5ComplianceExport:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        export = self.repo.create_compliance_export(org_id=org_id, user_id=user.id, export_type=str(data["export_type"]), filters=dict(data.get("filters") or {}))
        self.repo.create_advanced_audit_record(org_id=org_id, actor_user_id=user.id, event_type="compliance.export.created", resource_type="compliance_export", resource_id=export.id, risk_classification="high", metadata={"export_type": export.export_type})
        self.db.commit()
        return export

    def create_retention_rule(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5RetentionRule:
        org_id = str(data["org_id"])
        workspace_id = data.get("workspace_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin"})
            org_id = workspace.org_id
        else:
            self.require_org_role(user.id, org_id, ADMIN_ROLES)
        rule = self.repo.create_retention_rule(org_id=org_id, user_id=user.id, workspace_id=workspace_id, data_type=str(data["data_type"]), retention_days=int(data["retention_days"]), action=str(data.get("action") or "retain"))
        self.repo.create_advanced_audit_record(org_id=org_id, workspace_id=workspace_id, actor_user_id=user.id, event_type="retention.rule.created", resource_type="retention_rule", resource_id=rule.id, risk_classification="medium")
        self.db.commit()
        return rule

    def update_governance_settings(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5GovernanceSetting:
        org_id = str(data["org_id"])
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        settings = self.repo.upsert_governance_settings(org_id=org_id, user_id=user.id, settings=dict(data.get("settings") or {}))
        self.repo.create_advanced_audit_record(org_id=org_id, actor_user_id=user.id, event_type="governance.settings.updated", resource_type="governance_settings", resource_id=org_id, risk_classification="medium", metadata={"v3_governance_ref": settings.v3_governance_ref})
        self.db.commit()
        return settings

    def create_governance_workflow(self, *, user: models.V5User, data: dict[str, Any]) -> models.V5GovernanceApprovalWorkflow:
        org_id = str(data["org_id"])
        workspace_id = data.get("workspace_id")
        if workspace_id:
            workspace = self.require_workspace_role(user.id, str(workspace_id), {"owner", "admin"})
            org_id = workspace.org_id
        else:
            self.require_org_role(user.id, org_id, ADMIN_ROLES)
        workflow = self.repo.create_governance_workflow(org_id=org_id, user_id=user.id, workspace_id=workspace_id, data=data)
        self.repo.create_advanced_audit_record(org_id=org_id, workspace_id=workspace_id, actor_user_id=user.id, event_type="governance.approval_workflow.created", resource_type="governance_workflow", resource_id=workflow.id, risk_classification="medium")
        self.db.commit()
        return workflow

    def security_dashboard(self, *, user: models.V5User, org_id: str) -> dict[str, Any]:
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        records = self.repo.search_advanced_audit_records(org_id=org_id, limit=200)
        risk_summary: dict[str, int] = {}
        for record in records:
            risk_summary[record.risk_classification] = risk_summary.get(record.risk_classification, 0) + 1
        api_keys = self.repo.list_api_keys(org_ids=[org_id])
        integrations = self.repo.list_integration_connections(org_ids=[org_id])
        high_risk = risk_summary.get("high", 0)
        medium_risk = risk_summary.get("medium", 0)
        score = max(0, 100 - high_risk * 15 - medium_risk * 5)
        return {"org_id": org_id, "login_activity": len([r for r in records if r.event_type.startswith("auth.")]), "security_events": len(records), "policy_violations": len([r for r in records if "violation" in r.event_type]), "api_key_activity": sum(key.usage_count for key in api_keys), "integration_activity": len(integrations), "risk_summary": risk_summary, "security_score": score}

    def admin_portal(self, *, user: models.V5User, org_id: str) -> dict[str, Any]:
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        workspaces = self.repo.list_workspaces(user_id=user.id, org_id=org_id)
        members = self.db.query(models.V5OrganizationMember).filter(models.V5OrganizationMember.org_id == org_id).count()
        subscription = self.repo.get_subscription(org_id)
        diagnostic = self.repo.create_admin_diagnostic(org_id=org_id, user_id=user.id, diagnostic_type="admin.portal.view", status_value="ok", summary="Admin portal metadata generated", metadata={"framework": "v5"})
        security = self.security_dashboard(user=user, org_id=org_id)
        self.db.commit()
        return {"org_id": org_id, "users": members, "workspaces": len(workspaces), "billing": {"plan_key": subscription.plan_key if subscription else "free", "status": subscription.status if subscription else "none"}, "security": security, "diagnostics": [{"id": diagnostic.id, "status": diagnostic.status, "summary": diagnostic.summary}], "feature_flags": {"v5_product_layer": "enabled", "enterprise_governance": "metadata_only"}}

    def governance_dashboard(self, *, user: models.V5User, org_id: str) -> dict[str, Any]:
        self.require_org_role(user.id, org_id, ADMIN_ROLES)
        settings = self.db.get(models.V5GovernanceSetting, org_id)
        workflows = self.repo.list_governance_workflows(org_id=org_id)
        policies = self.repo.list_security_policies(org_id=org_id)
        return {"org_id": org_id, "settings": settings.settings_json if settings else {}, "v3_governance_ref": settings.v3_governance_ref if settings else "v3-governance", "approval_workflows": [{"id": workflow.id, "name": workflow.name, "status": workflow.status} for workflow in workflows], "policy_assignments": [{"id": policy.id, "name": policy.name, "policy_type": policy.policy_type} for policy in policies]}

    def analytics_dashboard(self, *, user: models.V5User, org_id: str) -> dict[str, Any]:
        self.require_org_member(user.id, org_id)
        status_counts = self.repo.workflow_status_counts(org_id=org_id)
        total = sum(status_counts.values())
        successes = status_counts.get("completed", 0)
        activities = self.repo.list_team_activity(org_id=org_id, limit=100)
        return {
            "org_id": org_id,
            "workflow_status": status_counts,
            "success_rate": (successes / total) if total else 0.0,
            "capability_usage": self.repo.capability_usage_counts(org_id=org_id),
            "workspace_workflows": self.repo.workspace_workflow_counts(org_id=org_id),
            "team_activity_count": len(activities),
            "trend": [{"label": status_value, "count": count} for status_value, count in sorted(status_counts.items())],
            "export": {"format": "json", "generated_at": datetime.utcnow().isoformat(), "scope": "org"},
        }

    def usage_dashboard(self, *, user: models.V5User, org_id: str) -> dict[str, Any]:
        self.require_org_member(user.id, org_id)
        records = self.repo.list_usage_records(org_id=org_id)
        totals: dict[str, int] = {}
        by_workspace: dict[str, dict[str, int]] = {}
        by_user: dict[str, dict[str, int]] = {}
        for record in records:
            totals[record.usage_type] = totals.get(record.usage_type, 0) + record.quantity
            if record.workspace_id:
                by_workspace.setdefault(record.workspace_id, {})
                by_workspace[record.workspace_id][record.usage_type] = by_workspace[record.workspace_id].get(record.usage_type, 0) + record.quantity
            if record.user_id:
                by_user.setdefault(record.user_id, {})
                by_user[record.user_id][record.usage_type] = by_user[record.user_id].get(record.usage_type, 0) + record.quantity
        return {"org_id": org_id, "totals": totals, "by_workspace": by_workspace, "by_user": by_user, "records": [usage_record_snapshot(record) for record in records[:100]]}

    def mark_notification_read(self, *, user: models.V5User, notification_id: str) -> models.V5Notification:
        notification = self.repo.get_notification(notification_id)
        if not notification or notification.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found")
        notification.read_at = datetime.utcnow()
        self.db.commit()
        return notification

    def update_user_preferences(self, *, user: models.V5User, preferences: dict[str, Any]) -> models.V5UserPreference:
        pref = user.preferences or models.V5UserPreference(user_id=user.id, preferences={})
        pref.preferences = {**(pref.preferences or {}), **preferences}
        pref.updated_at = datetime.utcnow()
        self.db.add(pref)
        self.repo.write_audit(event_type="settings.user.updated", actor_user_id=user.id, resource_type="user", resource_id=user.id)
        self.db.commit()
        return pref

    def update_workspace_settings(self, *, user: models.V5User, workspace_id: str, settings: dict[str, Any]) -> models.V5WorkspaceSetting:
        workspace = self.require_workspace_role(user.id, workspace_id, {"owner", "admin"})
        current = workspace.settings or models.V5WorkspaceSetting(workspace_id=workspace.id, settings={})
        current.settings = {**(current.settings or {}), **settings}
        current.updated_at = datetime.utcnow()
        self.db.add(current)
        self.repo.write_audit(event_type="settings.workspace.updated", actor_user_id=user.id, org_id=workspace.org_id, workspace_id=workspace.id, resource_type="workspace", resource_id=workspace.id)
        self.db.commit()
        return current

    def require_org_member(self, user_id: str, org_id: str) -> str:
        role = self.repo.org_role(org_id, user_id)
        if not role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="organization access denied")
        return role

    def require_org_role(self, user_id: str, org_id: str, allowed: set[str]) -> str:
        role = self.require_org_member(user_id, org_id)
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient organization role")
        return role

    def require_workspace_role(self, user_id: str, workspace_id: str, allowed: set[str]) -> models.V5Workspace:
        workspace = self.repo.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace not found")
        role = self.repo.workspace_role(workspace_id, user_id)
        if role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="workspace access denied")
        return workspace

    def require_task_access(self, user_id: str, task_id: str, write: bool) -> models.V5SavedTask:
        task = self.repo.get_saved_task(task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
        if task.owner_user_id == user_id:
            return task
        if task.workspace_id:
            self.require_workspace_role(user_id, task.workspace_id, WORKSPACE_WRITE_ROLES if write else {"owner", "admin", "member", "viewer"})
            return task
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="task access denied")

    def require_template_access(self, user_id: str, template_id: str, write: bool) -> models.V5Template:
        template = self.repo.get_template(template_id)
        if not template:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template not found")
        self.require_workspace_role(user_id, template.workspace_id, WORKSPACE_WRITE_ROLES if write else {"owner", "admin", "member", "viewer"})
        return template

    def require_team_admin(self, user_id: str, team_id: str) -> models.V5Team:
        team = self.repo.get_team(team_id)
        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="team not found")
        self.require_org_role(user_id, team.org_id, ADMIN_ROLES)
        return team

    def require_assistant_access(self, user_id: str, assistant_id: str, write: bool) -> models.V5Assistant:
        assistant = self.repo.get_assistant(assistant_id)
        if not assistant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assistant not found")
        self.require_org_role(user_id, assistant.org_id, ADMIN_ROLES if write else {"owner", "admin", "member"})
        return assistant

    def require_integration_access(self, user_id: str, connection_id: str, write: bool) -> models.V5IntegrationConnection:
        connection = self.repo.get_integration_connection(connection_id)
        if not connection:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration connection not found")
        if connection.workspace_id:
            self.require_workspace_role(user_id, connection.workspace_id, {"owner", "admin"} if write else {"owner", "admin", "member", "viewer"})
        else:
            self.require_org_role(user_id, connection.org_id, ADMIN_ROLES if write else {"owner", "admin", "member"})
        return connection

    def require_api_key_access(self, user_id: str, key_id: str, write: bool) -> models.V5ApiKey:
        key = self.repo.get_api_key(key_id)
        if not key:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
        if key.workspace_id:
            self.require_workspace_role(user_id, key.workspace_id, {"owner", "admin"} if write else {"owner", "admin", "member", "viewer"})
        else:
            self.require_org_role(user_id, key.org_id, ADMIN_ROLES if write else {"owner", "admin", "member"})
        return key

    def _issue_token(self, user: models.V5User) -> str:
        expires_at = security.session_expiry()
        placeholder = self.repo.create_session(user_id=user.id, token_hash=f"pending:{models.new_id()}", expires_at=expires_at)
        token = security.create_token(user.id, placeholder.id, expires_at)
        placeholder.token_hash = security.token_hash(token)
        return token


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "organization"


def template_snapshot(template: models.V5Template) -> dict[str, Any]:
    return {
        "title": template.title,
        "description": template.description,
        "parameter_schema": template.parameter_schema or {},
        "body": template.body or {},
    }


def _redact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(metadata)
    for key in ["password", "token", "secret", "authorization", "cookie"]:
        if key in redacted:
            redacted[key] = "[redacted]"
    return redacted


def usage_record_snapshot(record: models.V5UsageRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "workspace_id": record.workspace_id,
        "user_id": record.user_id,
        "workflow_run_id": record.workflow_run_id,
        "usage_type": record.usage_type,
        "quantity": record.quantity,
        "unit": record.unit,
        "created_at": record.created_at.isoformat(),
    }
