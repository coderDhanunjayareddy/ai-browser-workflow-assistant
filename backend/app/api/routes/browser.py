"""
V7.0 Live Browser Sync Layer — REST API.

7 endpoints:
  POST /browser/events              — ingest event (lightweight: no refresh engines)
  POST /browser/sync                — ingest + full refresh pipeline
  GET  /browser/events              — list recent events (?mission_id= &tab_id= &limit=)
  GET  /browser/events/{event_id}   — single event lookup
  GET  /browser/analytics           — counters
  GET  /browser/inspect/{mission_id}— full debug inspector
  GET  /browser/timeline/{mission_id}— chronological stream
"""
from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.browser import analytics as browser_analytics
from app.browser import registry as event_reg
from app.browser import timeline as tl
from app.browser import sync_service
from app.browser.inspector import inspect as do_inspect
from app.browser.models import BrowserEventPayload, BrowserEventType
from app.browser.persistence import save as persist_event
from app.schemas.browser import (
    BrowserAnalyticsSchema,
    BrowserEventRequest,
    BrowserEventSchema,
    BrowserInspectorSchema,
    BrowserSyncRequest,
    BrowserTimelineSchema,
    DecisionSignalSchema,
    SyncResultSchema,
)

router = APIRouter(prefix="/browser", tags=["V7.0 Browser Sync"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _request_to_payload(req: BrowserEventRequest) -> BrowserEventPayload:
    return BrowserEventPayload(
        event_type = req.event_type,
        tab_id     = req.tab_id,
        url        = req.url,
        title      = req.title,
        timestamp  = req.timestamp,
        mission_id = req.mission_id,
        task_id    = req.task_id,
        metadata   = req.metadata,
    )


# ── POST /browser/events — lightweight ingest ─────────────────────────────────

@router.post("/events", response_model=SyncResultSchema)
def ingest_event(req: BrowserEventRequest):
    """
    Ingest a browser event from the Chrome extension.
    Updates tab registry and timeline. Does NOT run refresh engines.
    Use POST /browser/sync when full refresh is needed.
    """
    payload = _request_to_payload(req)
    event   = payload.to_browser_event()

    # Register in event registry + timeline
    event_reg.register(event)
    if event.mission_id:
        tl.append(event.mission_id, event)
    else:
        tl.append_global(event)

    # Update analytics
    browser_analytics.record_event(event.event_type)

    # Persist (no-op when feature flag is off)
    persist_event(event)

    # Update tab registry via LiveSyncService
    sync_result = sync_service.process_event(event)

    return SyncResultSchema(**sync_result.to_dict())


# ── POST /browser/sync — ingest + full refresh pipeline ──────────────────────

@router.post("/sync", response_model=SyncResultSchema)
def sync_event(req: BrowserSyncRequest):
    """
    Ingest a browser event and run full refresh pipeline:
    tab registry → mission refresh → trust refresh → recommendation refresh.
    """
    payload = _request_to_payload(req)
    event   = payload.to_browser_event()

    event_reg.register(event)
    if event.mission_id:
        tl.append(event.mission_id, event)
    else:
        tl.append_global(event)

    browser_analytics.record_event(event.event_type)
    persist_event(event)

    sync_result = sync_service.process_event(event)

    mission_refresh_dict: Optional[dict] = None
    trust_refresh_dict:   Optional[dict] = None
    recommendations:      list[dict]     = []

    if sync_result.triggers_refresh and event.mission_id:
        mid = event.mission_id

        # Mission refresh
        try:
            from app.browser.mission_refresh import refresh as _mr
            mr = _mr(mid, reason=sync_result.refresh_reason)
            mission_refresh_dict = mr.to_dict()
            browser_analytics.record_mission_refresh()
        except Exception:
            pass

        # Trust refresh
        try:
            from app.browser.trust_refresh import refresh as _tr
            tr = _tr(mid)
            trust_refresh_dict = tr.to_dict()
            browser_analytics.record_trust_refresh()
        except Exception:
            pass

        # Recommendations
        try:
            from app.browser.recommendation import refresh as _rr
            sigs = _rr(mid)
            recommendations = [s.to_dict() for s in sigs]
            browser_analytics.record_recommendation_refresh()
        except Exception:
            pass

    result_dict = sync_result.to_dict()
    result_dict["mission_refresh"] = mission_refresh_dict
    result_dict["trust_refresh"]   = trust_refresh_dict
    result_dict["recommendations"] = recommendations

    return SyncResultSchema(**result_dict)


# ── GET /browser/events ───────────────────────────────────────────────────────

@router.get("/events", response_model=list[BrowserEventSchema])
def list_events(
    mission_id: Optional[str] = Query(None),
    tab_id:     Optional[str] = Query(None),
    limit:      int           = Query(50, ge=1, le=200),
):
    """List recent browser events, optionally filtered by mission or tab."""
    if mission_id:
        events = event_reg.events_for_mission(mission_id, limit=limit)
    elif tab_id:
        events = event_reg.events_for_tab(tab_id, limit=limit)
    else:
        events = event_reg.recent_events(limit=limit)
    return [BrowserEventSchema(**e.to_dict()) for e in events]


# ── GET /browser/events/{event_id} ───────────────────────────────────────────

@router.get("/events/{event_id}", response_model=BrowserEventSchema)
def get_event(event_id: str):
    """Retrieve a single browser event by ID."""
    ev = event_reg.get(event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found or expired.")
    return BrowserEventSchema(**ev.to_dict())


# ── GET /browser/analytics ────────────────────────────────────────────────────

@router.get("/analytics", response_model=BrowserAnalyticsSchema)
def get_analytics():
    """Browser event counters and refresh telemetry."""
    return BrowserAnalyticsSchema(**browser_analytics.get_analytics())


# ── GET /browser/inspect/{mission_id} ────────────────────────────────────────

@router.get("/inspect/{mission_id}", response_model=BrowserInspectorSchema)
def inspect_mission(
    mission_id:  str,
    event_limit: int = Query(20, ge=1, le=100),
):
    """
    Full debug inspector for a mission:
    recent events, tab state, trust, intelligence, recommendations, timeline.
    """
    import app.mission.store as ms
    if ms.get(mission_id) is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found.")
    result = do_inspect(mission_id, event_limit=event_limit)
    return BrowserInspectorSchema(**result)


# ── GET /browser/timeline/{mission_id} ───────────────────────────────────────

@router.get("/timeline/{mission_id}", response_model=BrowserTimelineSchema)
def get_timeline(
    mission_id: str,
    limit:      int = Query(50, ge=1, le=200),
):
    """Chronological browser event stream for a mission."""
    events = tl.get(mission_id, limit=limit)
    s      = tl.summary(mission_id)
    return BrowserTimelineSchema(
        mission_id   = mission_id,
        event_count  = s.get("event_count", 0),
        events       = events,
        type_counts  = s.get("type_counts", {}),
        latest_event = s.get("latest_event"),
    )
