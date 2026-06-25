"""
V7.0 Live Browser Sync Layer — Pydantic Schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Request bodies ────────────────────────────────────────────────────────────

class BrowserEventRequest(BaseModel):
    event_type: str
    tab_id:     str
    url:        Optional[str] = None
    title:      Optional[str] = None
    timestamp:  Optional[str] = None
    mission_id: Optional[str] = None
    task_id:    Optional[str] = None
    metadata:   dict[str, Any] = Field(default_factory=dict)


class BrowserSyncRequest(BrowserEventRequest):
    """Same as BrowserEventRequest — triggers full refresh pipeline."""
    pass


# ── Response schemas ──────────────────────────────────────────────────────────

class BrowserEventSchema(BaseModel):
    event_id:   str
    event_type: str
    tab_id:     str
    timestamp:  str
    url:        Optional[str] = None
    title:      Optional[str] = None
    mission_id: Optional[str] = None
    task_id:    Optional[str] = None
    metadata:   dict[str, Any] = Field(default_factory=dict)


class SyncResultSchema(BaseModel):
    success:          bool
    event_id:         str
    event_type:       str
    tab_updated:      bool            = False
    mission_id:       Optional[str]   = None
    triggers_refresh: bool            = False
    refresh_reason:   str             = ""
    latency_ms:       int             = 0
    error:            Optional[str]   = None
    # Enriched when POST /browser/sync is used
    mission_refresh:  Optional[dict]  = None
    trust_refresh:    Optional[dict]  = None
    recommendations:  list[dict]      = Field(default_factory=list)


class BrowserAnalyticsSchema(BaseModel):
    events_received:          int   = 0
    tab_created:              int   = 0
    tab_updated:              int   = 0
    tab_activated:            int   = 0
    tab_closed:               int   = 0
    url_changed:              int   = 0
    page_loaded:              int   = 0
    window_focused:           int   = 0
    window_blurred:           int   = 0
    mission_refreshes:        int   = 0
    trust_refreshes:          int   = 0
    recommendation_refreshes: int   = 0


class DecisionSignalSchema(BaseModel):
    signal_id:   str
    signal_type: str
    target_id:   str
    message:     str
    source:      str
    created_at:  str
    metadata:    dict[str, Any] = Field(default_factory=dict)


class BrowserInspectorSchema(BaseModel):
    mission_id:      str
    recent_events:   list[dict]       = Field(default_factory=list)
    tab_context:     Optional[dict]   = None
    tab_findings:    list[dict]       = Field(default_factory=list)
    trust:           Optional[dict]   = None
    intelligence:    Optional[dict]   = None
    recommendations: list[dict]       = Field(default_factory=list)
    timeline:        Optional[dict]   = None
    latency_ms:      int              = 0


class BrowserTimelineSchema(BaseModel):
    mission_id:    str
    event_count:   int           = 0
    events:        list[dict]    = Field(default_factory=list)
    type_counts:   dict[str,int] = Field(default_factory=dict)
    latest_event:  Optional[dict] = None


class RefreshResultSchema(BaseModel):
    mission_id:           str
    refreshed:            bool
    skipped_reason:       str            = ""
    readiness_score:      Optional[float] = None
    advisory_state:       Optional[str]   = None
    tab_count:            Optional[int]   = None
    trust_score:          Optional[float] = None
    risk_level:           Optional[str]   = None
    recommendation_count: int             = 0
    latency_ms:           int             = 0
