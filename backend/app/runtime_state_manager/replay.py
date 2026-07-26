from __future__ import annotations

from app.runtime_state_manager.models import RuntimeArtifact, RuntimeCheckpoint, RuntimeTab


def runtime_replay_frames(tabs: list[RuntimeTab], artifacts: list[RuntimeArtifact], checkpoint: RuntimeCheckpoint, *, session_id: str | None = None) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for tab in tabs[-12:]:
        frames.append({
            "event": "runtime.tab",
            "logical_tab": tab.logical_id,
            "runtime_tab": tab.runtime_id,
            "url": tab.url,
            "page_type": tab.page_type,
            "active": tab.active,
        })
    for artifact in artifacts[-12:]:
        frames.append({
            "event": "runtime.artifact",
            "logical_artifact": artifact.logical_id,
            "type": artifact.artifact_type,
            "phase": artifact.owner_phase,
            "status": artifact.completion_status,
        })
    frames.append({"event": "runtime.checkpoint", "checkpoint_id": checkpoint.checkpoint_id, "phase": checkpoint.current_phase})
    if session_id:
        from app.runtime_state_manager.entity_binding import entity_binding_trace

        for index, event in enumerate(entity_binding_trace(session_id, limit=12), 1):
            frames.append({
                "event": "runtime.entity_binding",
                "frame_id": f"runtime_entity_binding_{index}",
                "entity_id": event.get("entity_id"),
                "artifact_id": event.get("artifact_id"),
                "runtime_resource_id": event.get("runtime_resource_id"),
                "resolved_by": event.get("resolved_by"),
                "registry_version": event.get("registry_version"),
                "outcome": event.get("outcome"),
            })
    return frames[-30:]
