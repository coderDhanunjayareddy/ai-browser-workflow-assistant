"""
V6.0 Multi-Tab Coordination Layer — TabSnapshotManager.

In-memory snapshots of tab state at key lifecycle moments.
Follows the V4.6 snapshot pattern (app/unified/snapshot.py) but
stores in-memory rather than DB (V6.0 is in-memory-first).

Snapshot triggers:
  tab_registered   → when a tab is first registered to a mission
  tab_role_changed → when a tab's role changes (e.g., research → comparison)
  mission_linked   → when a tab is attached to a mission
  tab_closed       → final state snapshot before close

Snapshots are READ-ONLY copies. They do NOT alter tab state.
Thread-safe with RLock.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Optional

from app.tabs.models import BrowserTab
from app.tabs import analytics as tab_analytics


SNAPSHOT_TRIGGERS = {
    "tab_registered",
    "tab_role_changed",
    "mission_linked",
    "tab_closed",
}


def _build_context(tab: BrowserTab) -> dict:
    """Extract snapshot-worthy context from a BrowserTab."""
    return {
        "tab_id":     tab.tab_id,
        "url":        tab.url,
        "title":      tab.title,
        "role":       tab.role.value,
        "state":      tab.state.value,
        "mission_id": tab.mission_id,
        "task_id":    tab.task_id,
        "updated_at": tab.updated_at.isoformat(),
    }


class TabSnapshotManager:
    """
    In-memory snapshot store.

    Structure: { tab_id → list[snapshot_dict] } (newest-first insertion)
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: dict[str, list[dict]] = {}

    # ── Create ────────────────────────────────────────────────────────────────

    def create(self, tab: BrowserTab, trigger: str) -> Optional[str]:
        """
        Create a snapshot of the given tab.

        Returns snapshot_id or None if trigger is unrecognized.
        """
        if trigger not in SNAPSHOT_TRIGGERS:
            return None

        snapshot_id = (
            f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}-{str(uuid.uuid4())[:4]}"
        )
        context = _build_context(tab)
        context["snapshot_id"] = snapshot_id
        context["trigger"] = trigger
        context["created_at"] = datetime.utcnow().isoformat()

        with self._lock:
            if tab.tab_id not in self._store:
                self._store[tab.tab_id] = []
            # Newest-first
            self._store[tab.tab_id].insert(0, context)

        tab_analytics.record_snapshot()
        return snapshot_id

    # ── Load ──────────────────────────────────────────────────────────────────

    def load_latest(self, tab_id: str) -> Optional[dict]:
        """Return the most recent snapshot for a tab, or None."""
        with self._lock:
            snapshots = self._store.get(tab_id)
            if not snapshots:
                return None
            return dict(snapshots[0])

    def load_all(self, tab_id: str) -> list[dict]:
        """Return all snapshots for a tab, newest first."""
        with self._lock:
            return [dict(s) for s in self._store.get(tab_id, [])]

    def count(self, tab_id: str) -> int:
        with self._lock:
            return len(self._store.get(tab_id, []))

    def all_tab_ids(self) -> list[str]:
        """Tab IDs that have at least one snapshot."""
        with self._lock:
            return list(self._store.keys())

    # ── Testing ───────────────────────────────────────────────────────────────

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._store.clear()


# Module-level singleton
_manager = TabSnapshotManager()


def create(tab: BrowserTab, trigger: str) -> Optional[str]:
    return _manager.create(tab, trigger)


def load_latest(tab_id: str) -> Optional[dict]:
    return _manager.load_latest(tab_id)


def load_all(tab_id: str) -> list[dict]:
    return _manager.load_all(tab_id)


def count(tab_id: str) -> int:
    return _manager.count(tab_id)


def all_tab_ids() -> list[str]:
    return _manager.all_tab_ids()


def _reset_for_testing() -> None:
    _manager._reset_for_testing()
