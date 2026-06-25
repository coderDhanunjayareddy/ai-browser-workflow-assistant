"""
V4.5 Unified Task Graph — in-memory task store.

Thread-safe dict keyed by task_id.
Also maintains a secondary index keyed by conversation_id (1:1 for MVP).

Pattern mirrors CognitiveConversationManager._sessions and ResearchSession stores.
DB persistence is handled separately by the lifecycle manager.
"""
from __future__ import annotations

import threading
from typing import Optional

from app.unified.models import UnifiedTask


class TaskStore:
    """Thread-safe in-process store for UnifiedTask objects."""

    def __init__(self) -> None:
        self._tasks: dict[str, UnifiedTask] = {}
        self._conv_index: dict[str, str] = {}   # conversation_id → task_id
        self._lock = threading.Lock()

    # ── Write ─────────────────────────────────────────────────────────────────

    def put(self, task: UnifiedTask) -> None:
        with self._lock:
            self._tasks[task.task_id] = task
            self._conv_index[task.conversation_id] = task.task_id

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, task_id: str) -> Optional[UnifiedTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_by_conversation(self, conversation_id: str) -> Optional[UnifiedTask]:
        with self._lock:
            tid = self._conv_index.get(conversation_id)
            return self._tasks.get(tid) if tid else None

    def all(self) -> list[UnifiedTask]:
        with self._lock:
            return list(self._tasks.values())

    def count(self) -> int:
        with self._lock:
            return len(self._tasks)

    # ── Warmup ────────────────────────────────────────────────────────────────

    def warmup(self) -> int:
        """
        V4.6: Load all active tasks from DB into memory on server startup.
        Returns count of tasks loaded. No-op when persistence is disabled.
        """
        try:
            from app.unified.restoration import warmup as _warmup_from_db
            return _warmup_from_db()
        except Exception:
            return 0

    # ── Test helpers ──────────────────────────────────────────────────────────

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._tasks.clear()
            self._conv_index.clear()


# Module-level singleton
_store = TaskStore()


def put(task: UnifiedTask) -> None:
    _store.put(task)


def get(task_id: str) -> Optional[UnifiedTask]:
    return _store.get(task_id)


def get_by_conversation(conversation_id: str) -> Optional[UnifiedTask]:
    return _store.get_by_conversation(conversation_id)


def all_tasks() -> list[UnifiedTask]:
    return _store.all()


def count() -> int:
    return _store.count()


def warmup() -> int:
    return _store.warmup()


def _reset_for_testing() -> None:
    _store._reset_for_testing()
