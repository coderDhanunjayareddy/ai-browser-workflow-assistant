"""
V6.0 Multi-Tab Coordination Layer — TabRestorationService.

Restores the TabRegistry from snapshots after a process restart or
warm-up. Reuses the snapshot pattern from V4.6 (app/unified/restoration.py).

Restoration is always ADVISORY:
  - Restored tabs are marked BACKGROUND (not ACTIVE)
  - Mission/task links are re-established from snapshot data
  - Tab state is reconstructed from the most recent snapshot per tab
  - No side-effects; does not trigger workflows
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TabRestorationResult:
    tabs_restored:    int
    tabs_skipped:     int
    mission_links:    int
    task_links:       int
    errors:           list[str]

    @property
    def success(self) -> bool:
        return not self.errors


class TabRestorationService:
    """
    Rebuilds the TabRegistry from TabSnapshotManager data.

    Only the LATEST snapshot per tab_id is used for restoration.
    Tabs that have been CLOSED in their last snapshot are skipped.
    """

    def restore_all(self) -> TabRestorationResult:
        """
        Iterate all snapshots and rebuild tabs in the registry.
        Safe to call multiple times — existing tabs are updated, not duplicated.
        """
        from app.tabs import snapshot as snap_manager
        from app.tabs import registry as tab_reg
        from app.tabs.models import BrowserTabRole, BrowserTabState
        from app.tabs import analytics as tab_analytics

        restored    = 0
        skipped     = 0
        mission_lnk = 0
        task_lnk    = 0
        errors: list[str] = []

        for tab_id in snap_manager.all_tab_ids():
            try:
                ctx = snap_manager.load_latest(tab_id)
                if ctx is None:
                    skipped += 1
                    continue

                # Skip tabs whose last known state was CLOSED
                raw_state = ctx.get("state", "OPEN")
                if raw_state == "CLOSED":
                    skipped += 1
                    continue

                role_str  = ctx.get("role",  "REFERENCE")
                try:
                    role  = BrowserTabRole(role_str)
                except ValueError:
                    role  = BrowserTabRole.reference

                # Restored tabs come back as BACKGROUND — not ACTIVE
                tab = tab_reg.register(
                    tab_id     = tab_id,
                    url        = ctx.get("url",   ""),
                    title      = ctx.get("title", ""),
                    role       = role,
                    state      = BrowserTabState.background,
                    mission_id = ctx.get("mission_id"),
                    task_id    = ctx.get("task_id"),
                )

                if tab.mission_id:
                    mission_lnk += 1
                if tab.task_id:
                    task_lnk += 1

                tab_analytics.record_tab_restored()
                restored += 1

            except Exception as exc:
                errors.append(f"{tab_id}: {exc}")
                skipped += 1

        return TabRestorationResult(
            tabs_restored = restored,
            tabs_skipped  = skipped,
            mission_links = mission_lnk,
            task_links    = task_lnk,
            errors        = errors,
        )

    def restore_for_mission(self, mission_id: str) -> TabRestorationResult:
        """
        Restore only tabs that were linked to a specific mission.
        """
        from app.tabs import snapshot as snap_manager
        from app.tabs import registry as tab_reg
        from app.tabs.models import BrowserTabRole, BrowserTabState
        from app.tabs import analytics as tab_analytics

        restored    = 0
        skipped     = 0
        mission_lnk = 0
        task_lnk    = 0
        errors: list[str] = []

        for tab_id in snap_manager.all_tab_ids():
            try:
                ctx = snap_manager.load_latest(tab_id)
                if ctx is None or ctx.get("mission_id") != mission_id:
                    continue

                raw_state = ctx.get("state", "OPEN")
                if raw_state == "CLOSED":
                    skipped += 1
                    continue

                role_str = ctx.get("role", "REFERENCE")
                try:
                    role = BrowserTabRole(role_str)
                except ValueError:
                    role = BrowserTabRole.reference

                tab = tab_reg.register(
                    tab_id     = tab_id,
                    url        = ctx.get("url",   ""),
                    title      = ctx.get("title", ""),
                    role       = role,
                    state      = BrowserTabState.background,
                    mission_id = mission_id,
                    task_id    = ctx.get("task_id"),
                )

                if tab.mission_id:
                    mission_lnk += 1
                if tab.task_id:
                    task_lnk += 1

                tab_analytics.record_tab_restored()
                restored += 1

            except Exception as exc:
                errors.append(f"{tab_id}: {exc}")
                skipped += 1

        return TabRestorationResult(
            tabs_restored = restored,
            tabs_skipped  = skipped,
            mission_links = mission_lnk,
            task_links    = task_lnk,
            errors        = errors,
        )


# Module-level singleton
_service = TabRestorationService()


def restore_all() -> TabRestorationResult:
    return _service.restore_all()


def restore_for_mission(mission_id: str) -> TabRestorationResult:
    return _service.restore_for_mission(mission_id)


def warmup() -> int:
    """Called on application startup. Returns count of tabs restored."""
    result = _service.restore_all()
    if result.tabs_restored:
        logger.info(
            "V6.0 tab restoration: %d tabs restored, %d skipped, %d errors",
            result.tabs_restored, result.tabs_skipped, len(result.errors),
        )
    return result.tabs_restored
