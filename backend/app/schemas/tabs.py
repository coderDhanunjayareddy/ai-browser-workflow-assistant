"""
V6.0 Multi-Tab Coordination Layer — Pydantic Schemas.

Used for REST API serialization only.
All domain logic lives in app/tabs/*.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Core tab ──────────────────────────────────────────────────────────────────

class BrowserTabSchema(BaseModel):
    tab_id:     str
    url:        str
    title:      str
    role:       str               # BrowserTabRole value
    state:      str               # BrowserTabState value
    mission_id: Optional[str] = None
    task_id:    Optional[str] = None
    created_at: str = ""          # ISO-8601
    updated_at: str = ""          # ISO-8601

    model_config = {"from_attributes": True}


# ── Tab context (cross-tab aggregate) ─────────────────────────────────────────

class TabContextSchema(BaseModel):
    mission_id:               str
    tab_count:                int
    active_tab_count:         int
    tab_summaries:            list[dict[str, Any]] = Field(default_factory=list)
    roles_present:            list[str]             = Field(default_factory=list)
    primary_tab:              Optional[dict[str, Any]] = None
    active_tab:               Optional[dict[str, Any]] = None
    workflow_tab_present:     bool = False
    comparison_tab_present:   bool = False
    research_tab_present:     bool = False
    duplicate_urls:           list[str] = Field(default_factory=list)
    latency_ms:               int = 0


# ── Tab intelligence ──────────────────────────────────────────────────────────

class TabFindingSchema(BaseModel):
    code:        str
    description: str
    severity:    str
    tab_ids:     list[str] = Field(default_factory=list)


class TabIntelligenceSchema(BaseModel):
    mission_id:      str
    findings:        list[TabFindingSchema] = Field(default_factory=list)
    recommendations: list[str]             = Field(default_factory=list)
    tab_count:       int = 0
    has_issues:      bool = False
    finding_count:   int = 0


# ── Analytics ─────────────────────────────────────────────────────────────────

class TabAnalyticsSchema(BaseModel):
    tabs_created:       int = 0
    tabs_closed:        int = 0
    tabs_restored:      int = 0
    active_tabs:        int = 0
    tab_snapshots:      int = 0
    mission_tab_links:  int = 0
    task_tab_links:     int = 0
    context_builds:     int = 0
    intelligence_runs:  int = 0
    avg_latency_ms:     int = 0


# ── Sync contract (V6.5 extension integration) ────────────────────────────────

class TabSyncPayloadSchema(BaseModel):
    tab_id:     str
    url:        str
    title:      str
    active:     bool = False
    mission_id: Optional[str] = None
    task_id:    Optional[str] = None


# ── Inspector ─────────────────────────────────────────────────────────────────

class TabInspectorSchema(BaseModel):
    mission_id:     str
    tabs:           list[BrowserTabSchema] = Field(default_factory=list)
    tab_context:    Optional[TabContextSchema] = None
    intelligence:   Optional[TabIntelligenceSchema] = None
    latency_ms:     int = 0


# ── Request bodies ────────────────────────────────────────────────────────────

class RegisterTabRequest(BaseModel):
    tab_id:     str
    url:        str
    title:      str
    role:       str = "REFERENCE"
    state:      str = "OPEN"
    mission_id: Optional[str] = None
    task_id:    Optional[str] = None


class UpdateTabRequest(BaseModel):
    url:   Optional[str] = None
    title: Optional[str] = None
    role:  Optional[str] = None
    state: Optional[str] = None


class CloseTabRequest(BaseModel):
    tab_id: str
