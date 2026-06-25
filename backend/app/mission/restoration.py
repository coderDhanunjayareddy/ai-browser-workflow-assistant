"""
V5.0 Mission Layer — MissionRestorationService.

Restores a mission and ALL its tasks from persistence.

Restoration order:
  1. Check in-memory mission store (fast path)
  2. Load mission from DB (slow path)
  3. For each task_id, call task_restoration.restore(task_id)
  4. Populate in-memory mission store

Performance target: < 50ms p95 for missions with ≤ 5 tasks.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from app.mission.models import Mission
from app.mission import store as mission_store, analytics as mission_analytics

logger = logging.getLogger(__name__)


class MissionRestorationService:

    def restore(self, mission_id: str) -> Optional[Mission]:
        """
        Return a fully-hydrated Mission.
        Fast path: return from in-memory store.
        Slow path: load from DB, restore all tasks.
        """
        t0 = time.perf_counter()

        # Fast path
        existing = mission_store.get(mission_id)
        if existing is not None:
            return existing

        # Slow path — load from DB
        from app.mission import persistence as mission_persistence
        mission = mission_persistence.load(mission_id)
        if mission is None:
            return None

        # Restore each task
        self._restore_tasks(mission)

        # Populate store
        mission_store.put(mission)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "Restored mission %s (state=%s, tasks=%d) in %dms",
            mission_id, mission.state.value, len(mission.task_ids), latency_ms,
        )
        return mission

    def _restore_tasks(self, mission: Mission) -> None:
        """Restore each task in the mission. Failures are logged but don't abort."""
        try:
            from app.unified import restoration as task_restoration
            for task_id in mission.task_ids:
                try:
                    task_restoration.restore(task_id)
                except Exception:
                    logger.exception("mission restore: failed to restore task %s", task_id)
        except ImportError:
            logger.warning("mission restore: unified restoration not available")

    def warmup(self) -> int:
        """
        Load all active missions from DB into in-memory store.
        Called once on server startup. Returns count of missions loaded.
        """
        from app.mission import persistence as mission_persistence
        missions = mission_persistence.load_active()
        count = 0
        for mission in missions:
            try:
                self._restore_tasks(mission)
                mission_store.put(mission)
                count += 1
            except Exception:
                logger.exception("mission warmup: failed to restore mission %s", mission.mission_id)
        if count:
            logger.info("Mission warmup: loaded %d active missions", count)
        return count


_service = MissionRestorationService()


def restore(mission_id: str) -> Optional[Mission]:
    return _service.restore(mission_id)


def warmup() -> int:
    return _service.warmup()
