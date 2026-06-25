"""
V6.0 Multi-Tab Coordination Layer — TabRegistry.

Global in-memory store for ALL browser tabs known to the platform.
Thread-safe. Same dict + RLock pattern as app/mission/store.py.

A tab is registered here and optionally linked to a Mission and/or Task by ID.
The registry is the single source of truth — MissionTabMap and TaskTabMap
are computed views over this store (no separate data structures).

No autonomy. No tab switching. Observation and coordination only.
"""
from __future__ import annotations

import threading
from typing import Optional

from app.tabs.models import (
    BrowserTab, BrowserTabRole, BrowserTabState,
    ACTIVE_TAB_STATES, TERMINAL_TAB_STATES,
    create_tab,
)
from app.tabs import analytics as tab_analytics


class TabRegistry:
    """
    Global registry of browser tabs.

    Tabs are keyed by tab_id. The registry never auto-closes tabs —
    only explicit close() calls transition a tab to CLOSED.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tabs: dict[str, BrowserTab] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register(
        self,
        tab_id:     str,
        url:        str,
        title:      str,
        role:       BrowserTabRole,
        state:      BrowserTabState = BrowserTabState.open,
        mission_id: Optional[str]   = None,
        task_id:    Optional[str]   = None,
    ) -> BrowserTab:
        """
        Register a new tab or update an existing one.
        If the tab_id already exists, updates url/title/role/state.
        """
        with self._lock:
            if tab_id in self._tabs:
                existing = self._tabs[tab_id]
                existing.url   = url
                existing.title = title
                existing.role  = role
                existing.state = state
                if mission_id:
                    existing.mission_id = mission_id
                if task_id:
                    existing.task_id = task_id
                existing.touch()
                return existing

            tab = create_tab(
                url=url, title=title, role=role, state=state,
                mission_id=mission_id, task_id=task_id, tab_id=tab_id,
            )
            self._tabs[tab_id] = tab
            tab_analytics.record_tab_created()
            return tab

    # ── Update ────────────────────────────────────────────────────────────────

    def update(
        self,
        tab_id: str,
        url:        Optional[str]            = None,
        title:      Optional[str]            = None,
        role:       Optional[BrowserTabRole]  = None,
        state:      Optional[BrowserTabState] = None,
    ) -> Optional[BrowserTab]:
        """Update mutable fields of an existing tab. Returns None if not found."""
        with self._lock:
            tab = self._tabs.get(tab_id)
            if tab is None:
                return None
            if url is not None:
                tab.url = url
            if title is not None:
                tab.title = title
            if role is not None:
                tab.role = role
            if state is not None:
                tab.state = state
            tab.touch()
            return tab

    def set_active(self, tab_id: str) -> Optional[BrowserTab]:
        """Mark tab as ACTIVE and all others in same mission as BACKGROUND."""
        with self._lock:
            tab = self._tabs.get(tab_id)
            if tab is None:
                return None
            # Put mission siblings to BACKGROUND
            if tab.mission_id:
                for t in self._tabs.values():
                    if (
                        t.tab_id != tab_id
                        and t.mission_id == tab.mission_id
                        and t.state == BrowserTabState.active
                    ):
                        t.state = BrowserTabState.background
                        t.touch()
            tab.state = BrowserTabState.active
            tab.touch()
            return tab

    # ── Close ─────────────────────────────────────────────────────────────────

    def close(self, tab_id: str) -> bool:
        """Mark tab as CLOSED. Returns False if not found."""
        with self._lock:
            tab = self._tabs.get(tab_id)
            if tab is None:
                return False
            tab.state = BrowserTabState.closed
            tab.touch()
            tab_analytics.record_tab_closed()
            return True

    # ── Attach links ──────────────────────────────────────────────────────────

    def attach_mission(self, tab_id: str, mission_id: str) -> bool:
        """Link tab to a mission. Returns False if tab not found."""
        with self._lock:
            tab = self._tabs.get(tab_id)
            if tab is None:
                return False
            tab.mission_id = mission_id
            tab.touch()
            tab_analytics.record_mission_link()
            return True

    def attach_task(self, tab_id: str, task_id: str) -> bool:
        """Link tab to a task. Returns False if tab not found."""
        with self._lock:
            tab = self._tabs.get(tab_id)
            if tab is None:
                return False
            tab.task_id = task_id
            tab.touch()
            tab_analytics.record_task_link()
            return True

    def detach_mission(self, tab_id: str) -> bool:
        """Remove mission link. Returns False if tab not found."""
        with self._lock:
            tab = self._tabs.get(tab_id)
            if tab is None:
                return False
            tab.mission_id = None
            tab.touch()
            return True

    def detach_task(self, tab_id: str) -> bool:
        """Remove task link. Returns False if tab not found."""
        with self._lock:
            tab = self._tabs.get(tab_id)
            if tab is None:
                return False
            tab.task_id = None
            tab.touch()
            return True

    # ── Query ─────────────────────────────────────────────────────────────────

    def get(self, tab_id: str) -> Optional[BrowserTab]:
        with self._lock:
            return self._tabs.get(tab_id)

    def all(self) -> list[BrowserTab]:
        """All tabs including CLOSED."""
        with self._lock:
            return list(self._tabs.values())

    def all_open(self) -> list[BrowserTab]:
        """All non-closed tabs."""
        with self._lock:
            return [t for t in self._tabs.values() if t.state in ACTIVE_TAB_STATES]

    def for_mission(self, mission_id: str) -> list[BrowserTab]:
        """All tabs (including closed) linked to a mission."""
        with self._lock:
            return [t for t in self._tabs.values() if t.mission_id == mission_id]

    def open_for_mission(self, mission_id: str) -> list[BrowserTab]:
        """Open tabs linked to a mission."""
        with self._lock:
            return [
                t for t in self._tabs.values()
                if t.mission_id == mission_id and t.state in ACTIVE_TAB_STATES
            ]

    def for_task(self, task_id: str) -> list[BrowserTab]:
        """All tabs linked to a task."""
        with self._lock:
            return [t for t in self._tabs.values() if t.task_id == task_id]

    def open_for_task(self, task_id: str) -> list[BrowserTab]:
        """Open tabs linked to a task."""
        with self._lock:
            return [
                t for t in self._tabs.values()
                if t.task_id == task_id and t.state in ACTIVE_TAB_STATES
            ]

    def count(self) -> int:
        with self._lock:
            return len(self._tabs)

    def count_open(self) -> int:
        with self._lock:
            return sum(1 for t in self._tabs.values() if t.state in ACTIVE_TAB_STATES)

    # ── Testing ───────────────────────────────────────────────────────────────

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._tabs.clear()


# Module-level singleton
_registry = TabRegistry()


def register(
    tab_id:     str,
    url:        str,
    title:      str,
    role:       BrowserTabRole,
    state:      BrowserTabState = BrowserTabState.open,
    mission_id: Optional[str]   = None,
    task_id:    Optional[str]   = None,
) -> BrowserTab:
    return _registry.register(tab_id, url, title, role, state, mission_id, task_id)


def update(
    tab_id: str,
    url:    Optional[str]            = None,
    title:  Optional[str]            = None,
    role:   Optional[BrowserTabRole]  = None,
    state:  Optional[BrowserTabState] = None,
) -> Optional[BrowserTab]:
    return _registry.update(tab_id, url, title, role, state)


def set_active(tab_id: str) -> Optional[BrowserTab]:
    return _registry.set_active(tab_id)


def close(tab_id: str) -> bool:
    return _registry.close(tab_id)


def attach_mission(tab_id: str, mission_id: str) -> bool:
    return _registry.attach_mission(tab_id, mission_id)


def attach_task(tab_id: str, task_id: str) -> bool:
    return _registry.attach_task(tab_id, task_id)


def detach_mission(tab_id: str) -> bool:
    return _registry.detach_mission(tab_id)


def detach_task(tab_id: str) -> bool:
    return _registry.detach_task(tab_id)


def get(tab_id: str) -> Optional[BrowserTab]:
    return _registry.get(tab_id)


def all_tabs() -> list[BrowserTab]:
    return _registry.all()


def all_open() -> list[BrowserTab]:
    return _registry.all_open()


def for_mission(mission_id: str) -> list[BrowserTab]:
    return _registry.for_mission(mission_id)


def open_for_mission(mission_id: str) -> list[BrowserTab]:
    return _registry.open_for_mission(mission_id)


def for_task(task_id: str) -> list[BrowserTab]:
    return _registry.for_task(task_id)


def open_for_task(task_id: str) -> list[BrowserTab]:
    return _registry.open_for_task(task_id)


def count() -> int:
    return _registry.count()


def count_open() -> int:
    return _registry.count_open()


def _reset_for_testing() -> None:
    _registry._reset_for_testing()
