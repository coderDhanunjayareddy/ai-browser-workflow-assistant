from __future__ import annotations

import hashlib
import threading

from app.runtime_state_manager.models import RuntimeArtifact, RuntimeCheckpoint, RuntimeTab


class RuntimeCheckpointStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, RuntimeCheckpoint] = {}

    def save(self, session_id: str, checkpoint: RuntimeCheckpoint) -> None:
        with self._lock:
            self._items[session_id] = checkpoint

    def restore(self, session_id: str) -> RuntimeCheckpoint | None:
        with self._lock:
            return self._items.get(session_id)


def build_checkpoint(
    *,
    session_id: str,
    current_phase: str | None,
    tabs: list[RuntimeTab],
    artifacts: list[RuntimeArtifact],
    budgets: dict[str, int] | None = None,
    recovery_state: str = "none",
) -> RuntimeCheckpoint:
    opened = [tab.logical_id for tab in tabs if tab.lifecycle in {"active", "opened", "navigated"}]
    visited = []
    for tab in tabs:
        for url in tab.navigation_history:
            if url not in visited:
                visited.append(url)
    extraction_progress = {
        "artifacts": len(artifacts),
        "opened_pages": len([artifact for artifact in artifacts if artifact.artifact_type == "opened_page"]),
    }
    raw = f"{session_id}|{current_phase}|{opened}|{len(artifacts)}"
    return RuntimeCheckpoint(
        checkpoint_id=f"runtime_checkpoint_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}",
        current_phase=current_phase,
        opened_tabs=opened,
        visited_pages=visited[-30:],
        artifacts=[artifact.logical_id for artifact in artifacts],
        extraction_progress=extraction_progress,
        completed_entities=[],
        budgets=budgets or {},
        recovery_state=recovery_state,
    )
