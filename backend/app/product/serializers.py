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


def team_member_out(member: models.V5TeamMember) -> dict:
    return {"id": member.id, "team_id": member.team_id, "user_id": member.user_id, "role": member.role, "joined_at": member.joined_at}


def invitation_out(invitation: models.V5Invitation) -> dict:
    return {
        "id": invitation.id,
        "org_id": invitation.org_id,
        "team_id": invitation.team_id,
        "workspace_id": invitation.workspace_id,
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "token": invitation.token,
        "created_at": invitation.created_at,
    }


def team_activity_out(activity: models.V5TeamActivity) -> dict:
    return {
        "id": activity.id,
        "org_id": activity.org_id,
        "team_id": activity.team_id,
        "workspace_id": activity.workspace_id,
        "actor_user_id": activity.actor_user_id,
        "activity_type": activity.activity_type,
        "summary": activity.summary,
        "metadata": activity.metadata_json or {},
        "created_at": activity.created_at,
    }


def workspace_share_out(share: models.V5WorkspaceShare) -> dict:
    return {"id": share.id, "workspace_id": share.workspace_id, "org_id": share.org_id, "team_id": share.team_id, "role": share.role, "created_at": share.created_at}


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


def assistant_out(assistant: models.V5Assistant) -> dict:
    return {
        "id": assistant.id,
        "org_id": assistant.org_id,
        "name": assistant.name,
        "description": assistant.description,
        "instructions": assistant.instructions,
        "capability_permissions": assistant.capability_permissions or [],
        "status": assistant.status,
        "current_version": assistant.current_version,
        "metrics": assistant.metrics_json or {},
        "created_at": assistant.created_at,
        "updated_at": assistant.updated_at,
    }


def assistant_version_out(version: models.V5AssistantVersion) -> dict:
    return {
        "id": version.id,
        "assistant_id": version.assistant_id,
        "version_number": version.version_number,
        "name": version.name,
        "change_summary": version.change_summary,
        "created_at": version.created_at,
    }


def assistant_assignment_out(assignment: models.V5AssistantWorkspaceAssignment) -> dict:
    return {
        "id": assignment.id,
        "assistant_id": assignment.assistant_id,
        "workspace_id": assignment.workspace_id,
        "org_id": assignment.org_id,
        "role": assignment.role,
        "created_at": assignment.created_at,
    }


def integration_catalog_out(item: models.V5IntegrationCatalogItem) -> dict:
    return {
        "id": item.id,
        "provider_key": item.provider_key,
        "name": item.name,
        "category": item.category,
        "auth_type": item.auth_type,
        "scopes": item.scopes or [],
        "capabilities": item.capabilities or [],
        "status": item.status,
    }


def integration_connection_out(connection: models.V5IntegrationConnection) -> dict:
    return {
        "id": connection.id,
        "org_id": connection.org_id,
        "workspace_id": connection.workspace_id,
        "provider_key": connection.provider_key,
        "status": connection.status,
        "token_metadata": connection.token_metadata or {},
        "health_status": connection.health_status,
        "last_health_check_at": connection.last_health_check_at,
        "created_at": connection.created_at,
        "updated_at": connection.updated_at,
    }


def integration_health_out(event: models.V5IntegrationHealthEvent) -> dict:
    return {
        "id": event.id,
        "connection_id": event.connection_id,
        "status": event.status,
        "latency_ms": event.latency_ms,
        "message": event.message,
        "created_at": event.created_at,
    }


def usage_record_out(record: models.V5UsageRecord) -> dict:
    return {
        "id": record.id,
        "org_id": record.org_id,
        "workspace_id": record.workspace_id,
        "user_id": record.user_id,
        "workflow_run_id": record.workflow_run_id,
        "usage_type": record.usage_type,
        "quantity": record.quantity,
        "unit": record.unit,
        "metadata": record.metadata_json or {},
        "created_at": record.created_at,
    }
