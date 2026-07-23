from __future__ import annotations

from app.product import models


def user_out(user: models.V5User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "status": user.status,
        "preferences": (user.preferences.preferences if user.preferences else {}),
    }


def org_out(org: models.V5Organization, role: str | None = None) -> dict:
    return {"id": org.id, "name": org.name, "slug": org.slug, "role": role}


def team_out(team: models.V5Team) -> dict:
    return {"id": team.id, "org_id": team.org_id, "name": team.name, "created_at": team.created_at}


def workspace_out(workspace: models.V5Workspace, role: str | None = None) -> dict:
    return {
        "id": workspace.id,
        "org_id": workspace.org_id,
        "name": workspace.name,
        "description": workspace.description,
        "role": role,
        "status": workspace.status,
        "created_at": workspace.created_at,
    }


def workflow_out(run: models.V5WorkflowRun) -> dict:
    return {
        "id": run.id,
        "workspace_id": run.workspace_id,
        "org_id": run.org_id,
        "title": run.title,
        "status": run.status,
        "input_summary": run.input_summary,
        "output_summary": run.output_summary,
        "runtime_ref": run.runtime_ref,
        "browser_session_ref": run.browser_session_ref,
        "parameters": run.parameters_json or {},
        "created_at": run.created_at,
        "steps": [
            {
                "id": step.id,
                "step_index": step.step_index,
                "action_type": step.action_type,
                "status": step.status,
                "capability_id": step.capability_id,
                "validation_status": step.validation_status,
                "duration_ms": step.duration_ms,
                "metadata": step.metadata_json or {},
            }
            for step in sorted(run.steps, key=lambda s: s.step_index)
        ],
    }


def audit_out(event: models.V5AuditEvent) -> dict:
    return {
        "id": event.id,
        "org_id": event.org_id,
        "workspace_id": event.workspace_id,
        "actor_user_id": event.actor_user_id,
        "event_type": event.event_type,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "risk_level": event.risk_level,
        "metadata": event.metadata_json or {},
        "created_at": event.created_at,
    }


def replay_share_out(share: models.V5ReplayShare) -> dict:
    return {
        "id": share.id,
        "workflow_run_id": share.workflow_run_id,
        "share_token": share.share_token,
        "visibility": share.visibility,
        "redaction_policy": share.redaction_policy or {},
        "created_at": share.created_at,
    }


def saved_task_out(task: models.V5SavedTask) -> dict:
    return {
        "id": task.id,
        "org_id": task.org_id,
        "workspace_id": task.workspace_id,
        "scope": task.scope,
        "title": task.title,
        "description": task.description,
        "input_prompt": task.input_prompt,
        "parameters": task.parameters_json or {},
        "tags": task.tags or [],
        "favorite": task.favorite,
        "run_count": task.run_count,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def template_out(template: models.V5Template) -> dict:
    return {
        "id": template.id,
        "org_id": template.org_id,
        "workspace_id": template.workspace_id,
        "title": template.title,
        "description": template.description,
        "parameter_schema": template.parameter_schema or {},
        "body": template.body or {},
        "current_version": template.current_version,
        "forked_from_template_id": template.forked_from_template_id,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }


def template_version_out(version: models.V5TemplateVersion) -> dict:
    return {
        "id": version.id,
        "template_id": version.template_id,
        "version_number": version.version_number,
        "title": version.title,
        "change_summary": version.change_summary,
        "created_at": version.created_at,
    }


def resource_version_out(version: models.V5ResourceVersion) -> dict:
    return {
        "id": version.id,
        "org_id": version.org_id,
        "workspace_id": version.workspace_id,
        "resource_type": version.resource_type,
        "resource_id": version.resource_id,
        "version_number": version.version_number,
        "snapshot": version.snapshot_json or {},
        "diff": version.diff_metadata or {},
        "change_summary": version.change_summary,
        "rollback_of_version_id": version.rollback_of_version_id,
        "created_at": version.created_at,
    }


def notification_out(notification: models.V5Notification) -> dict:
    return {
        "id": notification.id,
        "org_id": notification.org_id,
        "workspace_id": notification.workspace_id,
        "event_type": notification.event_type,
        "title": notification.title,
        "body": notification.body,
        "metadata": notification.metadata_json or {},
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }
