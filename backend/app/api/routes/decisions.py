"""
V7.5 Decision Center — REST API routes.

Endpoints:
  GET  /decisions                          → list all decisions (filter: status, priority, limit)
  GET  /decisions/critical                 → critical decisions only
  GET  /decisions/analytics                → DecisionAnalytics counters
  GET  /decisions/inspect                  → full inspector (no mission filter)
  GET  /decisions/{decision_id}            → single decision
  GET  /decisions/mission/{mission_id}     → all decisions for a mission
  POST /decisions/aggregate/{mission_id}   → trigger aggregation for a mission
  POST /decisions/{decision_id}/acknowledge → mark acknowledged
  POST /decisions/{decision_id}/dismiss    → mark dismissed
  POST /decisions/{decision_id}/resolve    → mark resolved

Decision Center is informational only. No execution, no autonomy.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.decisions import registry as reg
from app.decisions import analytics as anal
from app.decisions import feed as decision_feed
from app.decisions import inspector as insp_module
from app.decisions import aggregator
from app.decisions import timeline as tl
from app.decisions.models import DecisionStatus
from app.schemas.decisions import (
    DecisionItemSchema, DecisionAnalyticsSchema, DecisionInspectorSchema,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decisions", tags=["decisions"])


def _to_schema(item) -> dict:
    return item.to_dict()


# ── GET /decisions ─────────────────────────────────────────────────────────────

@router.get("")
def list_decisions(
    status:     Optional[str] = Query(None),
    priority:   Optional[str] = Query(None),
    mission_id: Optional[str] = Query(None),
    limit:      int           = Query(50, ge=1, le=500),
):
    if mission_id:
        items = reg.list_for_mission(mission_id, limit=limit)
    else:
        items = reg.list_all(limit=limit)

    if status:
        try:
            st = DecisionStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
        items = [d for d in items if d.status == st]

    if priority:
        from app.decisions.models import DecisionPriority
        try:
            pr = DecisionPriority(priority.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown priority: {priority}")
        items = [d for d in items if d.priority == pr]

    return [_to_schema(d) for d in items[:limit]]


# ── GET /decisions/critical ────────────────────────────────────────────────────

@router.get("/critical")
def list_critical(limit: int = Query(20, ge=1, le=200)):
    return [_to_schema(d) for d in decision_feed.critical_only(limit)]


# ── GET /decisions/analytics ───────────────────────────────────────────────────

@router.get("/analytics")
def get_analytics():
    return anal.get_analytics()


# ── GET /decisions/inspect ─────────────────────────────────────────────────────

@router.get("/inspect")
def inspect_global():
    return insp_module.inspect(mission_id="")


# ── GET /decisions/{decision_id} ───────────────────────────────────────────────

@router.get("/{decision_id}")
def get_decision(decision_id: str):
    item = reg.get(decision_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    return _to_schema(item)


# ── GET /decisions/mission/{mission_id} ────────────────────────────────────────

@router.get("/mission/{mission_id}")
def decisions_for_mission(mission_id: str, limit: int = Query(100, ge=1, le=500)):
    items = reg.list_for_mission(mission_id, limit=limit)
    return [_to_schema(d) for d in items]


# ── POST /decisions/aggregate/{mission_id} ─────────────────────────────────────

@router.post("/aggregate/{mission_id}")
def aggregate_for_mission(mission_id: str):
    # Verify mission exists
    try:
        from app.mission import store as ms
        m = ms.get(mission_id)
        if m is None:
            raise HTTPException(status_code=404, detail=f"Mission {mission_id} not found")
    except HTTPException:
        raise
    except Exception:
        pass

    t0    = time.perf_counter()
    items = aggregator.aggregate(mission_id)
    ms_el = int((time.perf_counter() - t0) * 1000)
    return {
        "mission_id":     mission_id,
        "decisions_found": len(items),
        "latency_ms":     ms_el,
        "decisions":      [_to_schema(d) for d in items],
    }


# ── POST /decisions/{decision_id}/acknowledge ─────────────────────────────────

@router.post("/{decision_id}/acknowledge")
def acknowledge_decision(decision_id: str):
    ok = reg.update_status(decision_id, DecisionStatus.acknowledged)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    anal.record_acknowledged()
    item = reg.get(decision_id)
    tl.record(decision_id, "acknowledged",
              mission_id = item.mission_id or "" if item else "",
              priority   = item.priority.value   if item else "",
              title      = item.title             if item else "",
              source     = item.source            if item else "")
    return {"decision_id": decision_id, "status": "ACKNOWLEDGED"}


# ── POST /decisions/{decision_id}/dismiss ──────────────────────────────────────

@router.post("/{decision_id}/dismiss")
def dismiss_decision(decision_id: str):
    ok = reg.update_status(decision_id, DecisionStatus.dismissed)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    anal.record_dismissed()
    return {"decision_id": decision_id, "status": "DISMISSED"}


# ── POST /decisions/{decision_id}/resolve ──────────────────────────────────────

@router.post("/{decision_id}/resolve")
def resolve_decision(decision_id: str):
    item = reg.get(decision_id)
    duration_ms = 0.0
    if item and item.created_at:
        from datetime import datetime
        duration_ms = (datetime.utcnow() - item.created_at).total_seconds() * 1000
    ok = reg.update_status(decision_id, DecisionStatus.resolved)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found")
    anal.record_resolved(duration_ms)
    return {"decision_id": decision_id, "status": "RESOLVED"}
