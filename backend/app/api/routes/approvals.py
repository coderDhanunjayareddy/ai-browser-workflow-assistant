"""
V8.0 Human Approval Center — REST API routes.

Endpoints:
  GET  /approvals                          → list all approvals (filter: status, mission_id, limit)
  GET  /approvals/pending                  → pending only
  GET  /approvals/critical                 → high/critical pending
  GET  /approvals/analytics                → ApprovalAnalytics counters
  GET  /approvals/inspect                  → global inspector
  GET  /approvals/{approval_id}            → single approval
  GET  /approvals/mission/{mission_id}     → approvals for a mission
  POST /approvals/generate/{mission_id}    → trigger approval generation
  POST /approvals/{approval_id}/approve    → record human approval
  POST /approvals/{approval_id}/reject     → record human rejection
  POST /approvals/{approval_id}/cancel     → cancel pending approval

Approval Center records human decisions only. No execution. No autonomy.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.approvals import registry as reg
from app.approvals import analytics as anal
from app.approvals import queue as q_mod
from app.approvals import inspector as insp_module
from app.approvals import generator
from app.approvals import timeline as tl
from app.approvals.models import (
    ApprovalStatus, ApprovalRiskLevel, ApprovalDecisionContract,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/approvals", tags=["approvals"])


class _ApproveBody(BaseModel):
    decision_source: str = "human_via_api"


class _RejectBody(BaseModel):
    reason:          str = ""
    decision_source: str = "human_via_api"


# ── GET /approvals ─────────────────────────────────────────────────────────────

@router.get("")
def list_approvals(
    status:     Optional[str] = Query(None),
    mission_id: Optional[str] = Query(None),
    limit:      int           = Query(50, ge=1, le=500),
):
    if mission_id:
        items = reg.list_for_mission(mission_id, limit=limit)
    else:
        items = reg.list_all(limit=limit)

    if status:
        try:
            st = ApprovalStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
        items = [r for r in items if r.status == st]

    return [r.to_dict() for r in items[:limit]]


# ── GET /approvals/pending ────────────────────────────────────────────────────

@router.get("/pending")
def list_pending(limit: int = Query(50, ge=1, le=500)):
    return [r.to_dict() for r in q_mod.all_pending(limit=limit)]


# ── GET /approvals/critical ───────────────────────────────────────────────────

@router.get("/critical")
def list_critical(limit: int = Query(20, ge=1, le=200)):
    return [r.to_dict() for r in q_mod.critical(limit=limit)]


# ── GET /approvals/analytics ──────────────────────────────────────────────────

@router.get("/analytics")
def get_analytics():
    return anal.get_analytics()


# ── GET /approvals/inspect ────────────────────────────────────────────────────

@router.get("/inspect")
def inspect_global():
    return insp_module.inspect(mission_id="")


# ── GET /approvals/mission/{mission_id} ───────────────────────────────────────

@router.get("/mission/{mission_id}")
def approvals_for_mission(mission_id: str, limit: int = Query(100, ge=1, le=500)):
    items = q_mod.for_mission(mission_id, limit=limit)
    return [r.to_dict() for r in items]


# ── POST /approvals/generate/{mission_id} ─────────────────────────────────────

@router.post("/generate/{mission_id}")
def generate_for_mission(mission_id: str):
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
    items = generator.generate_for_mission(mission_id)
    for item in items:
        reg.add(item)
        anal.record_created(item.risk_level.value)
        tl.record(item.approval_id, "created",
                  mission_id = item.mission_id or "",
                  risk_level = item.risk_level.value,
                  title      = item.title,
                  source     = item.source_type.value)
    ms_el = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "mission_id":       mission_id,
        "approvals_found":  len(items),
        "latency_ms":       ms_el,
        "approvals":        [r.to_dict() for r in items],
    }


# ── GET /approvals/{approval_id} ──────────────────────────────────────────────

@router.get("/{approval_id}")
def get_approval(approval_id: str):
    item = reg.get(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")
    return item.to_dict()


# ── POST /approvals/{approval_id}/approve ─────────────────────────────────────

@router.post("/{approval_id}/approve")
def approve_approval(approval_id: str, body: _ApproveBody = _ApproveBody()):
    item = reg.get(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")
    if item.status != ApprovalStatus.pending:
        raise HTTPException(status_code=409,
                            detail=f"Approval is {item.status.value}, not PENDING")

    duration_ms = (time.time() - item.created_at) * 1000
    ok = reg.approve(approval_id, decision_source=body.decision_source)
    if not ok:
        raise HTTPException(status_code=409, detail="Could not approve — already resolved")

    anal.record_approved(duration_ms)
    tl.record(approval_id, "approved",
              mission_id = item.mission_id or "",
              risk_level = item.risk_level.value,
              title      = item.title,
              source     = body.decision_source)

    contract = ApprovalDecisionContract(
        approval_id     = approval_id,
        approved        = True,
        approved_at     = time.time(),
        decision_source = body.decision_source,
        mission_id      = item.mission_id,
        metadata        = {"risk_level": item.risk_level.value},
    )
    updated = reg.get(approval_id)

    # V8.5: Generate GovernanceContract from the approved request (non-blocking)
    gov_contract_dict = None
    try:
        from app.governance import generator as _gov_gen
        from app.governance import registry as _gov_reg
        from app.governance import analytics as _gov_anal
        from app.governance import timeline as _gov_tl
        gov_contract = _gov_gen.generate_from_approval(updated) if updated else None
        if gov_contract:
            _gov_reg.add(gov_contract)
            _gov_anal.record_created()
            _gov_tl.record(gov_contract.contract_id, "created",
                           mission_id  = gov_contract.mission_id or "",
                           risk_level  = gov_contract.risk_level,
                           source_type = gov_contract.source_type,
                           approved    = gov_contract.approved)
            gov_contract_dict = gov_contract.to_dict()
    except Exception:
        pass

    return {
        "approval_id":        approval_id,
        "status":             "APPROVED",
        "duration_ms":        round(duration_ms, 1),
        "contract":           contract.to_dict(),
        "governance_contract": gov_contract_dict,
        "approval":           updated.to_dict() if updated else None,
    }


# ── POST /approvals/{approval_id}/reject ──────────────────────────────────────

@router.post("/{approval_id}/reject")
def reject_approval(approval_id: str, body: _RejectBody = _RejectBody()):
    item = reg.get(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")
    if item.status != ApprovalStatus.pending:
        raise HTTPException(status_code=409,
                            detail=f"Approval is {item.status.value}, not PENDING")

    duration_ms = (time.time() - item.created_at) * 1000
    ok = reg.reject(approval_id, reason=body.reason, decision_source=body.decision_source)
    if not ok:
        raise HTTPException(status_code=409, detail="Could not reject — already resolved")

    anal.record_rejected(duration_ms)
    tl.record(approval_id, "rejected",
              mission_id = item.mission_id or "",
              risk_level = item.risk_level.value,
              title      = item.title,
              source     = body.decision_source)

    contract = ApprovalDecisionContract(
        approval_id     = approval_id,
        approved        = False,
        approved_at     = time.time(),
        decision_source = body.decision_source,
        mission_id      = item.mission_id,
        metadata        = {"rejection_reason": body.reason, "risk_level": item.risk_level.value},
    )
    updated = reg.get(approval_id)
    return {
        "approval_id":  approval_id,
        "status":       "REJECTED",
        "duration_ms":  round(duration_ms, 1),
        "contract":     contract.to_dict(),
        "approval":     updated.to_dict() if updated else None,
    }


# ── POST /approvals/{approval_id}/cancel ──────────────────────────────────────

@router.post("/{approval_id}/cancel")
def cancel_approval(approval_id: str):
    item = reg.get(approval_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id} not found")
    if item.status != ApprovalStatus.pending:
        raise HTTPException(status_code=409,
                            detail=f"Approval is {item.status.value}, not PENDING")

    ok = reg.cancel(approval_id)
    if not ok:
        raise HTTPException(status_code=409, detail="Could not cancel")

    anal.record_cancelled()
    tl.record(approval_id, "cancelled",
              mission_id = item.mission_id or "",
              risk_level = item.risk_level.value,
              title      = item.title,
              source     = "api")

    updated = reg.get(approval_id)
    return {
        "approval_id": approval_id,
        "status":      "CANCELLED",
        "approval":    updated.to_dict() if updated else None,
    }
