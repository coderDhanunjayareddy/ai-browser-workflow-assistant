from __future__ import annotations

import re
from datetime import datetime
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
        self.repo.write_audit(event_type="team.created", actor_user_id=user.id, org_id=org_id, resource_type="team", resource_id=team.id)
        self.db.commit()
        return team

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
