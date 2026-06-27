"""
V8.9 Browser Runtime Layer — RuntimeSessionRegistry.

In-memory store of RuntimeSessions. TTL: 1 hour of inactivity (sessions are
transient; a browser that goes quiet for an hour is considered gone).

Same RLock + monotonic pattern as the other V8.x registries.
NO persistence. NO execution.

Indexed by:
  runtime_id  → session
  mission_id  → set of runtime_ids
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.runtime.models import RuntimeSession, RuntimeState

TTL_SECONDS: float = 3600.0   # 1 hour of inactivity


class RuntimeSessionRegistry:

    def __init__(self, ttl: float = TTL_SECONDS) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        # runtime_id → (session, last_touch_monotonic)
        self._sessions: dict[str, tuple[RuntimeSession, float]] = {}
        # mission_id → set of runtime_ids
        self._by_mission: dict[str, set[str]] = {}
        self._total_added: int = 0
        self._total_evicted: int = 0

    # ── Write ────────────────────────────────────────────────────────────────

    def add(self, session: RuntimeSession) -> None:
        now = time.monotonic()
        with self._lock:
            self._evict_expired(now)
            self._sessions[session.runtime_id] = (session, now)
            if session.active_mission_id:
                self._by_mission.setdefault(session.active_mission_id, set()).add(session.runtime_id)
            self._total_added += 1

    def touch(self, runtime_id: str, wall_now: float) -> bool:
        """Mark a session active (resets TTL + updates updated_at)."""
        mono = time.monotonic()
        with self._lock:
            entry = self._sessions.get(runtime_id)
            if entry is None:
                return False
            session, _ = entry
            session.updated_at = wall_now
            self._sessions[runtime_id] = (session, mono)
            return True

    def update_session(
        self,
        runtime_id: str,
        *,
        wall_now:          float,
        browser_window_id: Optional[str] = None,
        active_tab_id:     Optional[str] = None,
        active_mission_id: Optional[str] = None,
        active_task_id:    Optional[str] = None,
        runtime_state:     Optional[RuntimeState] = None,
    ) -> Optional[RuntimeSession]:
        mono = time.monotonic()
        with self._lock:
            entry = self._sessions.get(runtime_id)
            if entry is None:
                return None
            session, _ = entry
            old_mission = session.active_mission_id
            if browser_window_id is not None:
                session.browser_window_id = browser_window_id
            if active_tab_id is not None:
                session.active_tab_id = active_tab_id
            if active_mission_id is not None:
                session.active_mission_id = active_mission_id
            if active_task_id is not None:
                session.active_task_id = active_task_id
            if runtime_state is not None:
                session.runtime_state = runtime_state
            session.updated_at = wall_now
            self._sessions[runtime_id] = (session, mono)
            # Re-index mission membership
            if active_mission_id is not None and active_mission_id != old_mission:
                if old_mission and old_mission in self._by_mission:
                    self._by_mission[old_mission].discard(runtime_id)
                self._by_mission.setdefault(active_mission_id, set()).add(runtime_id)
            return session

    def set_state(self, runtime_id: str, state: RuntimeState) -> bool:
        with self._lock:
            entry = self._sessions.get(runtime_id)
            if entry is None:
                return False
            entry[0].runtime_state = state
            return True

    # ── Read ─────────────────────────────────────────────────────────────────

    def get(self, runtime_id: str) -> Optional[RuntimeSession]:
        now = time.monotonic()
        with self._lock:
            entry = self._sessions.get(runtime_id)
            if entry is None:
                return None
            session, touched = entry
            if now - touched > self._ttl:
                self._remove_locked(runtime_id)
                self._total_evicted += 1
                return None
            return session

    def list_all(self, limit: int = 100) -> list[RuntimeSession]:
        now = time.monotonic()
        with self._lock:
            valid = [(s, t) for (s, t) in self._sessions.values() if now - t <= self._ttl]
        valid.sort(key=lambda pair: pair[1], reverse=True)
        return [s for s, _ in valid[:limit]]

    def list_for_mission(self, mission_id: str, limit: int = 100) -> list[RuntimeSession]:
        now = time.monotonic()
        with self._lock:
            ids = list(self._by_mission.get(mission_id, set()))
        result: list[RuntimeSession] = []
        for rid in ids:
            s = self.get(rid)
            if s is not None:
                result.append(s)
            if len(result) >= limit:
                break
        return result

    def count(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for (_, t) in self._sessions.values() if now - t <= self._ttl)

    def count_by_state(self, state: RuntimeState) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for (s, t) in self._sessions.values()
                       if now - t <= self._ttl and s.runtime_state == state)

    def summary_for_mission(self, mission_id: str) -> dict:
        sessions = self.list_for_mission(mission_id, limit=10000)
        active = sum(1 for s in sessions if s.runtime_state == RuntimeState.active)
        latest = max((s.updated_at for s in sessions), default=0.0)
        active_tab = sessions[0].active_tab_id if sessions else None
        return {
            "total_sessions":  len(sessions),
            "active_sessions": active,
            "active_tab_id":   active_tab,
            "latest_update":   latest,
            "runtime_ids":     [s.runtime_id for s in sessions],
        }

    # ── Housekeeping ─────────────────────────────────────────────────────────

    def _evict_expired(self, now: float) -> None:
        expired = [rid for rid, (_, t) in self._sessions.items() if now - t > self._ttl]
        for rid in expired:
            self._remove_locked(rid)
            self._total_evicted += 1

    def _remove_locked(self, runtime_id: str) -> None:
        entry = self._sessions.pop(runtime_id, None)
        if entry and entry[0].active_mission_id:
            s = self._by_mission.get(entry[0].active_mission_id)
            if s:
                s.discard(runtime_id)

    def stats(self) -> dict:
        now = time.monotonic()
        with self._lock:
            valid = sum(1 for (_, t) in self._sessions.values() if now - t <= self._ttl)
            return {
                "cached_sessions": valid,
                "total_added":     self._total_added,
                "total_evicted":   self._total_evicted,
                "mission_keys":    len(self._by_mission),
                "ttl_seconds":     self._ttl,
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._by_mission.clear()
            self._total_added   = 0
            self._total_evicted = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_registry = RuntimeSessionRegistry()


def add(session: RuntimeSession) -> None:                              _registry.add(session)
def touch(runtime_id: str, wall_now: float) -> bool:                   return _registry.touch(runtime_id, wall_now)
def update_session(runtime_id: str, **kwargs) -> Optional[RuntimeSession]: return _registry.update_session(runtime_id, **kwargs)
def set_state(runtime_id: str, state: RuntimeState) -> bool:           return _registry.set_state(runtime_id, state)
def get(runtime_id: str) -> Optional[RuntimeSession]:                  return _registry.get(runtime_id)
def list_all(limit: int = 100) -> list[RuntimeSession]:               return _registry.list_all(limit)
def list_for_mission(mission_id: str, limit: int = 100) -> list:      return _registry.list_for_mission(mission_id, limit)
def count() -> int:                                                   return _registry.count()
def count_by_state(state: RuntimeState) -> int:                       return _registry.count_by_state(state)
def summary_for_mission(mission_id: str) -> dict:                     return _registry.summary_for_mission(mission_id)
def stats() -> dict:                                                  return _registry.stats()
def _reset_for_testing() -> None:                                     _registry._reset_for_testing()
