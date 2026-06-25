"""
V4.6 Unified Task Graph — TaskRestorationService.

Reconstructs a full UnifiedTask from persisted records after a restart.

Restoration order:
  1. Check in-memory store (fast path — no DB hit needed)
  2. Load task metadata from UnifiedTaskRecord
  3. Reconstruct TaskTimeline from TaskTimelineRecord rows
  4. Reconstruct ApprovalRecord list from TaskApprovalRecord rows
  5. Optionally seed context from latest TaskSnapshotRecord
  6. Populate in-memory store
  7. Stamp restored_at on DB record

A single API call at GET /unified/tasks/{id}/restore returns the
fully restored task or a 404 if neither memory nor DB has it.

Performance target: < 50ms p95 for a typical task (≤ 50 timeline events).
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from app.unified import store as task_store
from app.unified import persistence as task_persistence
from app.unified import timeline_persistence
from app.unified import approval_persistence
from app.unified import snapshot as snapshot_system
from app.unified import analytics as task_analytics
from app.unified.models import UnifiedTask

logger = logging.getLogger(__name__)


class TaskRestorationService:
    """Restore a UnifiedTask from persistence into the in-memory store."""

    def restore(self, task_id: str) -> Optional[UnifiedTask]:
        """
        Return a fully-hydrated UnifiedTask.

        Fast path: return from in-memory store if already present.
        Slow path: load from DB, reconstruct, warm the store.

        Returns None if the task is not found anywhere.
        """
        t0 = time.perf_counter()

        # Fast path
        existing = task_store.get(task_id)
        if existing is not None:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            task_analytics.record_restoration_hit(latency_ms)
            return existing

        # Slow path — load from DB
        task = task_persistence.load(task_id)
        if task is None:
            return None

        # Hydrate timeline
        timeline = timeline_persistence.load_timeline(task_id)
        task.timeline = timeline

        # Hydrate approvals
        approvals = approval_persistence.load_all(task_id)
        task.approvals = approvals

        # Seed context from latest snapshot (if available)
        snap = snapshot_system.load_latest(task_id)
        if snap:
            if not task.entities and snap.get("entities"):
                task.entities = snap["entities"]
            if not task.research_report and snap.get("research_report"):
                task.research_report = snap["research_report"]
            if not task.execution_plan and snap.get("execution_plan"):
                task.execution_plan = snap["execution_plan"]

        # Warm the in-memory store
        task_store.put(task)

        # Stamp restored_at on DB
        task_persistence.mark_restored(task_id)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        task_analytics.record_restored_task(latency_ms)
        logger.info(
            "Restored task %s (state=%s, timeline=%d events, approvals=%d) in %dms",
            task_id, task.state.value, len(timeline.events), len(approvals), latency_ms,
        )
        return task

    def restore_by_conversation(self, conversation_id: str) -> Optional[UnifiedTask]:
        """Restore a task given its conversation_id."""
        # Fast path
        existing = task_store.get_by_conversation(conversation_id)
        if existing is not None:
            return existing

        # Load from DB by conversation_id
        task = task_persistence.load_by_conversation(conversation_id)
        if task is None:
            return None

        return self.restore(task.task_id)

    def warmup(self) -> int:
        """
        Load all active (non-terminal) tasks from DB into the in-memory store.
        Called once on server startup. Returns count of tasks loaded.
        """
        tasks = task_persistence.load_active()
        count = 0
        for task in tasks:
            try:
                # Hydrate sub-objects
                task.timeline = timeline_persistence.load_timeline(task.task_id)
                task.approvals = approval_persistence.load_all(task.task_id)

                snap = snapshot_system.load_latest(task.task_id)
                if snap:
                    if not task.entities and snap.get("entities"):
                        task.entities = snap["entities"]
                    if not task.research_report and snap.get("research_report"):
                        task.research_report = snap["research_report"]
                    if not task.execution_plan and snap.get("execution_plan"):
                        task.execution_plan = snap["execution_plan"]

                task_store.put(task)
                count += 1
            except Exception:
                logger.exception("warmup: failed to restore task %s", task.task_id)

        if count:
            logger.info("Warmup: loaded %d active tasks from DB into memory", count)
        return count


# Module-level singleton
_service = TaskRestorationService()


def restore(task_id: str) -> Optional[UnifiedTask]:
    return _service.restore(task_id)


def restore_by_conversation(conversation_id: str) -> Optional[UnifiedTask]:
    return _service.restore_by_conversation(conversation_id)


def warmup() -> int:
    return _service.warmup()
