from __future__ import annotations

from app.runtime_state_manager.models import LogicalResource, RuntimeArtifact, RuntimeTab, RuntimeWindow


def build_logical_resources(
    *,
    tabs: list[RuntimeTab],
    windows: list[RuntimeWindow],
    artifacts: list[RuntimeArtifact],
) -> list[LogicalResource]:
    resources: list[LogicalResource] = []
    for window in windows:
        resources.append(
            LogicalResource(
                logical_id=window.logical_id,
                resource_type="window",
                runtime_id=window.runtime_id,
                current_url=None,
                mission_entity_id=None,
                page_type=None,
                status="active" if window.active else "available",
                metadata={"tab_count": str(len(window.tab_ids))},
            )
        )
    for tab in tabs:
        resources.append(
            LogicalResource(
                logical_id=tab.logical_id,
                resource_type="tab",
                runtime_id=tab.runtime_id,
                current_url=tab.url,
                mission_entity_id=None,
                page_type=tab.page_type,
                status="active" if tab.active else "available",
                metadata={"title": tab.title[:160], "window_id": tab.window_id},
            )
        )
    for artifact in artifacts:
        resources.append(
            LogicalResource(
                logical_id=artifact.logical_id,
                resource_type="artifact",
                runtime_id=None,
                current_url=artifact.producing_page,
                mission_entity_id=None,
                page_type=None,
                status="completed" if artifact.completion_status == "complete" else "available",
                metadata={"artifact_type": artifact.artifact_type, "owner_phase": artifact.owner_phase},
            )
        )
    return resources
