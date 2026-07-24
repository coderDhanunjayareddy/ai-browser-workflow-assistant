from __future__ import annotations

import threading

from app.execution_continuity.models import ContinuitySnapshot


class ContinuityStateStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshots: dict[str, ContinuitySnapshot] = {}

    def save(self, snapshot: ContinuitySnapshot) -> None:
        with self._lock:
            self._snapshots[snapshot.session_id] = snapshot

    def get(self, session_id: str) -> ContinuitySnapshot | None:
        with self._lock:
            return self._snapshots.get(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._snapshots.pop(session_id, None)
