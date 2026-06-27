"""
V8.9 Browser Runtime Layer — REST API routes.

Endpoints:
  GET  /runtime                 → list runtime sessions (filter: mission_id, state)
  GET  /runtime/context         → mission-aware RuntimeContext (?runtime_id=)
  GET  /runtime/events          → runtime events (?runtime_id= or global)
  GET  /runtime/cache           → cached ContextSnapshot (?runtime_id=)
  GET  /runtime/analytics       → runtime analytics
  GET  /runtime/inspect         → full inspector (?runtime_id=)
  POST /runtime/sync            → incremental context sync

The Browser Runtime OBSERVES / SYNCS / PREDICTS / CACHES.
It does NOT execute, dispatch workflows, automate the browser, or call an LLM.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.runtime import registry as session_reg
from app.runtime import cache as ctx_cache
from app.runtime import events as event_queue
from app.runtime import analytics as anal
from app.runtime import context as runtime_context
from app.runtime import inspector as insp_module
from app.runtime import sync_service
from app.runtime.models import RuntimeState
from app.schemas.runtime import RuntimeSyncRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runtime", tags=["runtime"])


# ── GET /runtime ──────────────────────────────────────────────────────────────

@router.get("")
def list_sessions(
    mission_id: Optional[str] = Query(None),
    state:      Optional[str] = Query(None),
    limit:      int           = Query(50, ge=1, le=500),
):
    if mission_id:
        sessions = session_reg.list_for_mission(mission_id, limit=limit)
    else:
        sessions = session_reg.list_all(limit=limit)

    if state:
        try:
            st = RuntimeState(state.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown runtime state: {state}")
        sessions = [s for s in sessions if s.runtime_state == st]

    return [s.to_dict() for s in sessions[:limit]]


# ── GET /runtime/context ──────────────────────────────────────────────────────

@router.get("/context")
def get_context(runtime_id: str = Query(...)):
    if session_reg.get(runtime_id) is None:
        raise HTTPException(status_code=404, detail=f"Runtime {runtime_id} not found")
    return runtime_context.build(runtime_id).to_dict()


# ── GET /runtime/events ───────────────────────────────────────────────────────

@router.get("/events")
def get_events(
    runtime_id: Optional[str] = Query(None),
    limit:      int           = Query(50, ge=1, le=500),
):
    if runtime_id:
        events = event_queue.get_for_runtime(runtime_id, limit=limit)
    else:
        events = event_queue.recent_global(limit=limit)
    return [e.to_dict() for e in events]


# ── GET /runtime/cache ────────────────────────────────────────────────────────

@router.get("/cache")
def get_cache(runtime_id: str = Query(...)):
    snap = ctx_cache.peek(runtime_id)
    if snap is None:
        raise HTTPException(
            status_code=404,
            detail=f"No cached context for runtime {runtime_id}"
        )
    return {
        "runtime_id":  runtime_id,
        "snapshot":    snap.to_dict(),
        "age_seconds": ctx_cache.age_seconds(runtime_id),
        "is_fresh":    ctx_cache.is_fresh(runtime_id),
    }


# ── GET /runtime/analytics ────────────────────────────────────────────────────

@router.get("/analytics")
def get_analytics():
    return anal.get_analytics(wall_now=time.time())


# ── GET /runtime/inspect ──────────────────────────────────────────────────────

@router.get("/inspect")
def inspect_runtime(runtime_id: str = Query(...)):
    if session_reg.get(runtime_id) is None:
        raise HTTPException(status_code=404, detail=f"Runtime {runtime_id} not found")
    return insp_module.inspect(runtime_id)


# ── POST /runtime/sync ────────────────────────────────────────────────────────

@router.post("/sync")
def sync_runtime(body: RuntimeSyncRequest):
    result = sync_service.sync(
        runtime_id           = body.runtime_id,
        browser_window_id    = body.browser_window_id,
        active_tab_id        = body.active_tab_id,
        active_mission_id    = body.active_mission_id,
        active_task_id       = body.active_task_id,
        last_read_view       = body.last_read_view,
        last_dom_summary     = body.last_dom_summary,
        last_selection       = body.last_selection,
        last_url             = body.last_url,
        last_title           = body.last_title,
        last_scroll_position = body.last_scroll_position,
        dom_mutation_count   = body.dom_mutation_count,
    )
    return result.to_dict()
