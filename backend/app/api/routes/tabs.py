"""
V6.0 Multi-Tab Coordination Layer — REST API Routes.

Endpoints:
  GET  /tabs                              → list all open tabs
  GET  /tabs/analytics                    → tab analytics
  GET  /tabs/{tab_id}                     → get single tab
  GET  /tabs/mission/{mission_id}         → all tabs for a mission
  GET  /tabs/task/{task_id}               → all tabs for a task
  POST /tabs/register                     → register a tab
  POST /tabs/{tab_id}/update              → update tab fields
  POST /tabs/{tab_id}/close               → close a tab
  GET  /tabs/inspect/{mission_id}         → full inspector (context + intelligence)

All endpoints are observation/coordination only. No execution. No automation.
"""
import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.tabs import registry as tab_registry
from app.tabs import analytics as tab_analytics
from app.tabs import snapshot as tab_snapshot
from app.tabs.context import build as build_tab_context
from app.tabs.intelligence import analyze as analyze_tabs
from app.tabs import mission_tab_map, task_tab_map
from app.tabs.models import BrowserTabRole, BrowserTabState
from app.schemas.tabs import (
    BrowserTabSchema,
    TabContextSchema,
    TabAnalyticsSchema,
    TabIntelligenceSchema,
    TabFindingSchema,
    TabInspectorSchema,
    RegisterTabRequest,
    UpdateTabRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tabs", tags=["tabs"])


# ── Serialization helper ──────────────────────────────────────────────────────

def _tab_schema(tab) -> BrowserTabSchema:
    return BrowserTabSchema(
        tab_id     = tab.tab_id,
        url        = tab.url,
        title      = tab.title,
        role       = tab.role.value,
        state      = tab.state.value,
        mission_id = tab.mission_id,
        task_id    = tab.task_id,
        created_at = tab.created_at.isoformat(),
        updated_at = tab.updated_at.isoformat(),
    )


def _ctx_schema(ctx) -> TabContextSchema:
    return TabContextSchema(
        mission_id             = ctx.mission_id,
        tab_count              = ctx.tab_count,
        active_tab_count       = ctx.active_tab_count,
        tab_summaries          = ctx.tab_summaries,
        roles_present          = ctx.roles_present,
        primary_tab            = ctx.primary_tab,
        active_tab             = ctx.active_tab,
        workflow_tab_present   = ctx.workflow_tab_present,
        comparison_tab_present = ctx.comparison_tab_present,
        research_tab_present   = ctx.research_tab_present,
        duplicate_urls         = ctx.duplicate_urls,
        latency_ms             = ctx.latency_ms,
    )


def _intel_schema(result) -> TabIntelligenceSchema:
    return TabIntelligenceSchema(
        mission_id      = result.mission_id,
        findings        = [
            TabFindingSchema(
                code        = f.code,
                description = f.description,
                severity    = f.severity.value,
                tab_ids     = f.tab_ids,
            )
            for f in result.findings
        ],
        recommendations = result.recommendations,
        tab_count       = result.tab_count,
        has_issues      = result.has_issues,
        finding_count   = len(result.findings),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/analytics", response_model=TabAnalyticsSchema)
def get_tab_analytics():
    """Return tab coordination analytics counters."""
    data = tab_analytics.get_analytics()
    return TabAnalyticsSchema(**data)


@router.get("/mission/{mission_id}", response_model=list[BrowserTabSchema])
def get_tabs_for_mission(mission_id: str):
    """Return all open tabs linked to a mission."""
    tabs = mission_tab_map.list_open(mission_id)
    return [_tab_schema(t) for t in tabs]


@router.get("/task/{task_id}", response_model=list[BrowserTabSchema])
def get_tabs_for_task(task_id: str):
    """Return all open tabs linked to a task."""
    tabs = task_tab_map.list_open(task_id)
    return [_tab_schema(t) for t in tabs]


@router.get("/inspect/{mission_id}", response_model=TabInspectorSchema)
def inspect_tabs(mission_id: str):
    """
    Full inspector view for a mission's tabs.
    Returns tab list, cross-tab context, and advisory intelligence.
    """
    t0 = time.perf_counter()

    open_tabs = mission_tab_map.list_open(mission_id)
    tab_ctx   = build_tab_context(mission_id)

    # Advisory intelligence (readiness_score=0 — inspector does not run V5.5 engine)
    intel_result = analyze_tabs(tab_ctx)

    latency_ms = int((time.perf_counter() - t0) * 1000)

    return TabInspectorSchema(
        mission_id   = mission_id,
        tabs         = [_tab_schema(t) for t in open_tabs],
        tab_context  = _ctx_schema(tab_ctx),
        intelligence = _intel_schema(intel_result),
        latency_ms   = latency_ms,
    )


@router.get("/{tab_id}", response_model=BrowserTabSchema)
def get_tab(tab_id: str):
    """Return a single tab by ID."""
    tab = tab_registry.get(tab_id)
    if tab is None:
        raise HTTPException(status_code=404, detail=f"Tab {tab_id!r} not found.")
    return _tab_schema(tab)


@router.get("/", response_model=list[BrowserTabSchema])
def list_all_tabs():
    """Return all open (non-closed) tabs."""
    return [_tab_schema(t) for t in tab_registry.all_open()]


@router.post("/register", response_model=BrowserTabSchema)
def register_tab(req: RegisterTabRequest):
    """Register a tab in the coordination layer."""
    try:
        role  = BrowserTabRole(req.role.upper())
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"Unknown role {req.role!r}."
        )
    try:
        state = BrowserTabState(req.state.upper())
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"Unknown state {req.state!r}."
        )

    tab = tab_registry.register(
        tab_id     = req.tab_id,
        url        = req.url,
        title      = req.title,
        role       = role,
        state      = state,
        mission_id = req.mission_id,
        task_id    = req.task_id,
    )

    # Snapshot the registration event
    tab_snapshot.create(tab, "tab_registered")

    return _tab_schema(tab)


@router.post("/{tab_id}/update", response_model=BrowserTabSchema)
def update_tab(tab_id: str, req: UpdateTabRequest):
    """Update mutable fields of an existing tab."""
    role  = None
    state = None

    if req.role is not None:
        try:
            role = BrowserTabRole(req.role.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown role {req.role!r}.")

    if req.state is not None:
        try:
            state = BrowserTabState(req.state.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown state {req.state!r}.")

    tab = tab_registry.update(tab_id, url=req.url, title=req.title, role=role, state=state)
    if tab is None:
        raise HTTPException(status_code=404, detail=f"Tab {tab_id!r} not found.")

    # Snapshot role change
    if req.role is not None:
        tab_snapshot.create(tab, "tab_role_changed")

    return _tab_schema(tab)


@router.post("/{tab_id}/close", response_model=dict)
def close_tab(tab_id: str):
    """Mark a tab as CLOSED."""
    tab = tab_registry.get(tab_id)
    if tab is None:
        raise HTTPException(status_code=404, detail=f"Tab {tab_id!r} not found.")

    # Snapshot before close
    tab_snapshot.create(tab, "tab_closed")

    success = tab_registry.close(tab_id)
    return {"tab_id": tab_id, "closed": success}
