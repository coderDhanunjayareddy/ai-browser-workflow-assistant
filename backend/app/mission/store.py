"""
V5.0 Mission Layer — In-Memory Mission Store.

Thread-safe dict-based store. DB is write-through only.
Same pattern as app/unified/store.py.
"""
from __future__ import annotations

import threading
from typing import Optional

from app.mission.models import Mission, MissionState, TERMINAL_MISSION_STATES


class MissionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._missions: dict[str, Mission] = {}

    def put(self, mission: Mission) -> None:
        with self._lock:
            self._missions[mission.mission_id] = mission

    def get(self, mission_id: str) -> Optional[Mission]:
        with self._lock:
            return self._missions.get(mission_id)

    def all(self) -> list[Mission]:
        with self._lock:
            return list(self._missions.values())

    def active(self) -> list[Mission]:
        with self._lock:
            return [m for m in self._missions.values() if not m.is_terminal]

    def remove(self, mission_id: str) -> bool:
        with self._lock:
            return self._missions.pop(mission_id, None) is not None

    def find_by_task(self, task_id: str) -> Optional[Mission]:
        """Return the mission that owns task_id (first match)."""
        with self._lock:
            for m in self._missions.values():
                if task_id in m.task_ids:
                    return m
            return None

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._missions.clear()


_store = MissionStore()


def put(mission: Mission) -> None:
    _store.put(mission)


def get(mission_id: str) -> Optional[Mission]:
    return _store.get(mission_id)


def all_missions() -> list[Mission]:
    return _store.all()


def active_missions() -> list[Mission]:
    return _store.active()


def remove(mission_id: str) -> bool:
    return _store.remove(mission_id)


def find_by_task(task_id: str) -> Optional[Mission]:
    return _store.find_by_task(task_id)


def warmup() -> int:
    """Load all non-terminal missions from DB. Called once on startup."""
    from app.mission import persistence as mission_persistence
    missions = mission_persistence.load_active()
    for m in missions:
        _store.put(m)
    return len(missions)


def _reset_for_testing() -> None:
    _store._reset_for_testing()
