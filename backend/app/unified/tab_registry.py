"""
V4.5 Unified Task Graph — TaskTabRegistry.

Foundation layer for cross-tab awareness.

This component ONLY tracks which tabs participated in a UnifiedTask.
It does NOT implement multi-tab automation, cross-tab coordination,
or any form of autonomous tab control.

V5.0 will build multi-tab coordination on top of this foundation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.unified.models import TaskTab, TabRole, UnifiedTask
from app.unified import store as task_store


class TaskTabRegistry:
    """Track browser tabs that participate in a UnifiedTask."""

    # ── Register ──────────────────────────────────────────────────────────────

    def register(
        self,
        task: UnifiedTask,
        tab_id: str,
        url: str,
        title: str,
        role: TabRole,
    ) -> TaskTab:
        """
        Register a tab as participating in this task.
        If the tab_id already exists, update its URL, title, and role.
        """
        existing = self._find(task, tab_id)
        if existing is not None:
            existing.url = url
            existing.title = title
            existing.role = role
        else:
            existing = TaskTab(
                tab_id=tab_id,
                url=url,
                title=title,
                role=role,
            )
            task.tabs.append(existing)

        task.touch()
        task_store.put(task)
        return existing

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_by_role(self, task: UnifiedTask, role: TabRole) -> list[TaskTab]:
        return [t for t in task.tabs if t.role == role]

    def get_all(self, task: UnifiedTask) -> list[TaskTab]:
        return list(task.tabs)

    def get(self, task: UnifiedTask, tab_id: str) -> Optional[TaskTab]:
        return self._find(task, tab_id)

    def summary(self, task: UnifiedTask) -> list[dict]:
        return [
            {
                "tab_id": t.tab_id,
                "url": t.url,
                "title": t.title,
                "role": t.role.value,
                "added_at": t.added_at.isoformat(),
            }
            for t in task.tabs
        ]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _find(self, task: UnifiedTask, tab_id: str) -> Optional[TaskTab]:
        for t in task.tabs:
            if t.tab_id == tab_id:
                return t
        return None


# Module-level singleton
_registry = TaskTabRegistry()


def register(task: UnifiedTask, tab_id: str, url: str, title: str, role: TabRole) -> TaskTab:
    return _registry.register(task, tab_id, url, title, role)


def get_by_role(task: UnifiedTask, role: TabRole) -> list[TaskTab]:
    return _registry.get_by_role(task, role)


def get_all(task: UnifiedTask) -> list[TaskTab]:
    return _registry.get_all(task)


def get(task: UnifiedTask, tab_id: str) -> Optional[TaskTab]:
    return _registry.get(task, tab_id)


def summary(task: UnifiedTask) -> list[dict]:
    return _registry.summary(task)
