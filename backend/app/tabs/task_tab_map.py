"""
V6.0 Multi-Tab Coordination Layer — TaskTabMap.

Computed view over TabRegistry — NO separate storage.
Bridges V6.0 BrowserTab to V4.5 TaskTab (via TaskTabRegistry).

For Task → Tab relationships.
"""
from __future__ import annotations

from typing import Optional

from app.tabs.models import BrowserTab, BrowserTabRole
from app.tabs import registry as tab_registry


class TaskTabMap:
    """
    View of all tabs associated with a given task.
    Reads from TabRegistry — no separate storage.
    """

    # ── Attach / detach ───────────────────────────────────────────────────────

    def attach(self, task_id: str, tab_id: str) -> bool:
        """Link a tab to a task. Returns False if tab not found."""
        return tab_registry.attach_task(tab_id, task_id)

    def detach(self, task_id: str, tab_id: str) -> bool:
        """Remove the task link from a tab."""
        tab = tab_registry.get(tab_id)
        if tab is None or tab.task_id != task_id:
            return False
        return tab_registry.detach_task(tab_id)

    # ── Query ─────────────────────────────────────────────────────────────────

    def list_all(self, task_id: str) -> list[BrowserTab]:
        """All tabs (including closed) for this task."""
        return tab_registry.for_task(task_id)

    def list_open(self, task_id: str) -> list[BrowserTab]:
        """Open tabs for this task."""
        return tab_registry.open_for_task(task_id)

    def by_role(self, task_id: str, role: BrowserTabRole) -> list[BrowserTab]:
        """Open tabs for a task that match a given role."""
        return [
            t for t in tab_registry.open_for_task(task_id)
            if t.role == role
        ]

    def summary(self, task_id: str) -> list[dict]:
        """Serializable summary of open tabs for a task."""
        return [t.to_summary() for t in tab_registry.open_for_task(task_id)]

    def count(self, task_id: str) -> int:
        """Number of open tabs for this task."""
        return len(tab_registry.open_for_task(task_id))


# Module-level singleton
_map = TaskTabMap()


def attach(task_id: str, tab_id: str) -> bool:
    return _map.attach(task_id, tab_id)


def detach(task_id: str, tab_id: str) -> bool:
    return _map.detach(task_id, tab_id)


def list_all(task_id: str) -> list[BrowserTab]:
    return _map.list_all(task_id)


def list_open(task_id: str) -> list[BrowserTab]:
    return _map.list_open(task_id)


def by_role(task_id: str, role: BrowserTabRole) -> list[BrowserTab]:
    return _map.by_role(task_id, role)


def summary(task_id: str) -> list[dict]:
    return _map.summary(task_id)


def count(task_id: str) -> int:
    return _map.count(task_id)
