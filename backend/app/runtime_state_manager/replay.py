from __future__ import annotations

from app.runtime_state_manager.models import RuntimeArtifact, RuntimeCheckpoint, RuntimeTab


def runtime_replay_frames(tabs: list[RuntimeTab], artifacts: list[RuntimeArtifact], checkpoint: RuntimeCheckpoint) -> list[dict[str, object]]:
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
    return frames[-30:]
