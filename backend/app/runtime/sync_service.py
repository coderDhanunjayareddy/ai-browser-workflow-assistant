"""
V8.9 Browser Runtime Layer — RuntimeSyncService.

The orchestrator behind POST /runtime/sync.

Flow (pure infrastructure — no execution, no LLM, no network):
  1. Get-or-create the RuntimeSession.
  2. Build a new ContextSnapshot from the incoming payload.
  3. Read the previously-cached snapshot (cache hit / miss).
  4. Compute the incremental ContextDiff (only changed fields).
  5. Detect lightweight RuntimeEvents (content + session level).
  6. Enqueue the events.
  7. Update the cache with the new snapshot.
  8. Update the session (tab / mission / task / state).
  9. Run the heuristic PredictivePrefetch.
  10. Record analytics.
  11. Return diff + events + prefetch + mission-aware RuntimeContext.

The Chrome extension stays a thin observer; all intelligence here is deterministic.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.runtime import analytics as anal
from app.runtime import cache as ctx_cache
from app.runtime import context as runtime_context
from app.runtime import detector
from app.runtime import diff as diff_engine
from app.runtime import events as event_queue
from app.runtime import prefetch as prefetch_engine
from app.runtime import registry as session_reg
from app.runtime.models import (
    ContextSnapshot,
    RuntimeEvent,
    RuntimeSession,
    RuntimeState,
    make_session,
)


@dataclass
class SyncResult:
    runtime_id:   str
    created:      bool
    cache_hit:    bool
    diff:         dict[str, Any]
    events:       list[dict]            = field(default_factory=list)
    prefetch:     Optional[dict]        = None
    context:      Optional[dict]        = None
    session:      Optional[dict]        = None
    latency_ms:   float                 = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "created":    self.created,
            "cache_hit":  self.cache_hit,
            "diff":       self.diff,
            "events":     self.events,
            "prefetch":   self.prefetch,
            "context":    self.context,
            "session":    self.session,
            "latency_ms": self.latency_ms,
        }


class RuntimeSyncService:

    def sync(
        self,
        *,
        runtime_id:          Optional[str] = None,
        browser_window_id:   Optional[str] = None,
        active_tab_id:       Optional[str] = None,
        active_mission_id:   Optional[str] = None,
        active_task_id:      Optional[str] = None,
        last_read_view:      Optional[str] = None,
        last_dom_summary:    Optional[str] = None,
        last_selection:      Optional[str] = None,
        last_url:            Optional[str] = None,
        last_title:          Optional[str] = None,
        last_scroll_position: Optional[int] = None,
        dom_mutation_count:  int           = 0,
    ) -> SyncResult:
        t0       = time.perf_counter()
        wall_now = time.time()
        mono_now = time.monotonic()

        # 1. Get-or-create session
        session = session_reg.get(runtime_id) if runtime_id else None
        created = False
        if session is None:
            session = make_session(
                runtime_id        = runtime_id,
                browser_window_id = browser_window_id,
                active_tab_id     = active_tab_id,
                active_mission_id = active_mission_id,
                active_task_id    = active_task_id,
                now               = wall_now,
            )
            session_reg.add(session)
            created = True

        rid             = session.runtime_id
        old_tab_id      = session.active_tab_id
        old_mission_id  = session.active_mission_id
        old_task_id     = session.active_task_id

        # 2. New snapshot from payload
        new_snapshot = ContextSnapshot(
            last_read_view       = last_read_view,
            last_dom_summary     = last_dom_summary,
            last_selection       = last_selection,
            last_url             = last_url,
            last_title           = last_title,
            last_scroll_position = last_scroll_position,
            cached_at            = wall_now,
            dom_mutation_count   = dom_mutation_count,
        )

        # 3. Previous cached snapshot (counts hit/miss)
        old_snapshot = ctx_cache.get(rid)
        cache_hit    = old_snapshot is not None

        # 4. Incremental diff
        diff = diff_engine.compute(old_snapshot, new_snapshot)

        # 5. Detect events
        detected: list[RuntimeEvent] = detector.detect(
            rid, old_snapshot, new_snapshot,
            now            = wall_now,
            mission_id     = active_mission_id if active_mission_id is not None else old_mission_id,
            task_id        = active_task_id if active_task_id is not None else old_task_id,
            tab_id         = active_tab_id if active_tab_id is not None else old_tab_id,
            old_tab_id     = old_tab_id,
            old_mission_id = old_mission_id,
            old_task_id    = old_task_id,
        )

        # 6. Enqueue events
        event_queue.enqueue_many(detected)

        # 7. Update cache
        ctx_cache.set(rid, new_snapshot)

        # 8. Update session (state ACTIVE after a successful sync)
        session_reg.update_session(
            rid,
            wall_now          = wall_now,
            browser_window_id = browser_window_id,
            active_tab_id     = active_tab_id,
            active_mission_id = active_mission_id,
            active_task_id    = active_task_id,
            runtime_state     = RuntimeState.active,
        )

        # 9. Heuristic prefetch (uses this runtime's recent events + new context)
        recent = event_queue.get_for_runtime(rid, limit=50)
        hint   = prefetch_engine.predict(session_reg.get(rid), recent, new_snapshot)

        # 10. Analytics
        anal.record_sync(
            wall_now    = wall_now,
            cache_hit   = cache_hit,
            diff_ratio  = diff.diff_ratio,
            event_count = len(detected),
            prefetch    = hint.is_actionable,
        )

        # 11. Mission-aware context
        ctx = runtime_context.build(rid)

        latency_ms = (time.perf_counter() - t0) * 1000
        return SyncResult(
            runtime_id = rid,
            created    = created,
            cache_hit  = cache_hit,
            diff       = diff.to_dict(),
            events     = [e.to_dict() for e in detected],
            prefetch   = hint.to_dict(),
            context    = ctx.to_dict(),
            session    = session_reg.get(rid).to_dict() if session_reg.get(rid) else None,
            latency_ms = round(latency_ms, 3),
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_service = RuntimeSyncService()


def sync(**kwargs) -> SyncResult:
    return _service.sync(**kwargs)
