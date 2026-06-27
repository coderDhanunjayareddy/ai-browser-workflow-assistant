"""
V8.9 Browser Runtime Layer — Pydantic API Schemas.

Serializable representations for the /runtime endpoints.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── RuntimeSession ────────────────────────────────────────────────────────────

class RuntimeSessionSchema(BaseModel):
    runtime_id:        str
    browser_window_id: Optional[str] = None
    active_tab_id:     Optional[str] = None
    active_mission_id: Optional[str] = None
    active_task_id:    Optional[str] = None
    runtime_state:     str           = "IDLE"
    created_at:        float         = 0.0
    updated_at:        float         = 0.0


# ── ContextSnapshot / Cache ───────────────────────────────────────────────────

class ContextSnapshotSchema(BaseModel):
    last_read_view:       Optional[str] = None
    last_dom_summary:     Optional[str] = None
    last_selection:       Optional[str] = None
    last_url:             Optional[str] = None
    last_title:           Optional[str] = None
    last_scroll_position: Optional[int] = None
    cached_at:            float         = 0.0
    dom_mutation_count:   int           = 0


# ── ContextDiff ───────────────────────────────────────────────────────────────

class ContextDiffSchema(BaseModel):
    added:               dict[str, Any] = Field(default_factory=dict)
    removed:             dict[str, Any] = Field(default_factory=dict)
    modified:            dict[str, Any] = Field(default_factory=dict)
    changed_field_count: int            = 0
    has_changes:         bool           = False
    diff_ratio:          float          = 0.0


# ── RuntimeEvent ──────────────────────────────────────────────────────────────

class RuntimeEventSchema(BaseModel):
    event_id:   str
    event_type: str
    runtime_id: str
    timestamp:  float          = 0.0
    mission_id: Optional[str]  = None
    task_id:    Optional[str]  = None
    tab_id:     Optional[str]  = None
    detail:     dict[str, Any] = Field(default_factory=dict)


# ── PrefetchHint ──────────────────────────────────────────────────────────────

class PrefetchHintSchema(BaseModel):
    prefetch_type: str            = "NONE"
    reason:        str            = ""
    confidence:    float          = 0.0
    is_actionable: bool           = False
    signals:       dict[str, Any] = Field(default_factory=dict)


# ── RuntimeContext ────────────────────────────────────────────────────────────

class RuntimeContextSchema(BaseModel):
    runtime_id:          str
    active_mission_id:   Optional[str]  = None
    active_task_id:      Optional[str]  = None
    mission_state:       Optional[str]  = None
    approval_state:      Optional[dict] = None
    authorization_state: Optional[dict] = None
    execution_ready:     bool           = False
    evaluated_at:        float          = 0.0


# ── Analytics ─────────────────────────────────────────────────────────────────

class RuntimeAnalyticsSchema(BaseModel):
    runtime_uptime_seconds: float = 0.0
    syncs:                  int   = 0
    cached_requests:        int   = 0
    cache_hits:             int   = 0
    cache_misses:           int   = 0
    cache_hit_ratio:        float = 0.0
    avg_context_diff_ratio: float = 0.0
    prefetch_opportunities: int   = 0
    total_events:           int   = 0
    event_rate:             float = 0.0


# ── Inspector ─────────────────────────────────────────────────────────────────

class RuntimeInspectorSchema(BaseModel):
    runtime_id:            str
    session:               Optional[dict] = None
    cache_health:          dict           = Field(default_factory=dict)
    context_freshness:     dict           = Field(default_factory=dict)
    event_summary:         dict           = Field(default_factory=dict)
    recent_events:         list           = Field(default_factory=list)
    prefetch:              dict           = Field(default_factory=dict)
    runtime_context:       dict           = Field(default_factory=dict)
    authorization_runtime: dict           = Field(default_factory=dict)
    browser_sync:          Optional[dict] = None
    analytics:             dict           = Field(default_factory=dict)
    registry_stats:        dict           = Field(default_factory=dict)
    cache_stats:           dict           = Field(default_factory=dict)
    queue_stats:           dict           = Field(default_factory=dict)
    latency_ms:            float          = 0.0


# ── POST /runtime/sync request / response ─────────────────────────────────────

class RuntimeSyncRequest(BaseModel):
    runtime_id:           Optional[str] = None
    browser_window_id:    Optional[str] = None
    active_tab_id:        Optional[str] = None
    active_mission_id:    Optional[str] = None
    active_task_id:       Optional[str] = None
    last_read_view:       Optional[str] = None
    last_dom_summary:     Optional[str] = None
    last_selection:       Optional[str] = None
    last_url:             Optional[str] = None
    last_title:           Optional[str] = None
    last_scroll_position: Optional[int] = None
    dom_mutation_count:   int           = 0


class RuntimeSyncResponse(BaseModel):
    runtime_id: str
    created:    bool                  = False
    cache_hit:  bool                  = False
    diff:       ContextDiffSchema
    events:     list[RuntimeEventSchema] = Field(default_factory=list)
    prefetch:   Optional[PrefetchHintSchema] = None
    context:    Optional[RuntimeContextSchema] = None
    session:    Optional[RuntimeSessionSchema] = None
    latency_ms: float                 = 0.0
