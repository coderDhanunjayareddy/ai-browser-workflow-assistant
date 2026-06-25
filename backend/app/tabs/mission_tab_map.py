"""
V6.0 Multi-Tab Coordination Layer — MissionTabMap.

Computed view over TabRegistry — NO separate storage.
All operations are O(n) scans over the global tab list.

For Mission → Tab relationships.
"""
from __future__ import annotations

from typing import Optional

from app.tabs.models import BrowserTab, BrowserTabRole, BrowserTabState
from app.tabs import registry as tab_registry


class MissionTabMap:
    """
    View of all tabs associated with a given mission.
    Never duplicates data — always reads from TabRegistry.
    """

    # ── Attach / detach ───────────────────────────────────────────────────────

    def attach(self, mission_id: str, tab_id: str) -> bool:
        """Link a tab to a mission. Returns False if tab not found."""
        return tab_registry.attach_mission(tab_id, mission_id)

    def detach(self, mission_id: str, tab_id: str) -> bool:
        """Remove the mission link from a tab."""
        tab = tab_registry.get(tab_id)
        if tab is None or tab.mission_id != mission_id:
            return False
        return tab_registry.detach_mission(tab_id)

    # ── Query ─────────────────────────────────────────────────────────────────

    def list_all(self, mission_id: str) -> list[BrowserTab]:
        """All tabs (including closed) for this mission."""
        return tab_registry.for_mission(mission_id)

    def list_open(self, mission_id: str) -> list[BrowserTab]:
        """Open (non-closed) tabs for this mission."""
        return tab_registry.open_for_mission(mission_id)

    def primary_tab(self, mission_id: str) -> Optional[BrowserTab]:
        """Return the PRIMARY-role tab for this mission, or None."""
        for t in tab_registry.open_for_mission(mission_id):
            if t.role == BrowserTabRole.primary:
                return t
        return None

    def active_tab(self, mission_id: str) -> Optional[BrowserTab]:
        """Return the currently ACTIVE tab for this mission, or None."""
        for t in tab_registry.open_for_mission(mission_id):
            if t.state == BrowserTabState.active:
                return t
        return None

    def by_role(self, mission_id: str, role: BrowserTabRole) -> list[BrowserTab]:
        """Return all open tabs for a mission that match a given role."""
        return [
            t for t in tab_registry.open_for_mission(mission_id)
            if t.role == role
        ]

    def summary(self, mission_id: str) -> list[dict]:
        """Serializable summary of open tabs for this mission."""
        return [t.to_summary() for t in tab_registry.open_for_mission(mission_id)]

    def count(self, mission_id: str) -> int:
        """Number of open tabs for this mission."""
        return len(tab_registry.open_for_mission(mission_id))


# Module-level singleton
_map = MissionTabMap()


def attach(mission_id: str, tab_id: str) -> bool:
    return _map.attach(mission_id, tab_id)


def detach(mission_id: str, tab_id: str) -> bool:
    return _map.detach(mission_id, tab_id)


def list_all(mission_id: str) -> list[BrowserTab]:
    return _map.list_all(mission_id)


def list_open(mission_id: str) -> list[BrowserTab]:
    return _map.list_open(mission_id)


def primary_tab(mission_id: str) -> Optional[BrowserTab]:
    return _map.primary_tab(mission_id)


def active_tab(mission_id: str) -> Optional[BrowserTab]:
    return _map.active_tab(mission_id)


def by_role(mission_id: str, role: BrowserTabRole) -> list[BrowserTab]:
    return _map.by_role(mission_id, role)


def summary(mission_id: str) -> list[dict]:
    return _map.summary(mission_id)


def count(mission_id: str) -> int:
    return _map.count(mission_id)
