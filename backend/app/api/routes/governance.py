"""
V8.5 Governance Layer — REST API routes.

Endpoints:
  GET  /governance/contracts                    → list all (filter: status, mission_id, limit)
  GET  /governance/contracts/active             → ACTIVE contracts only
  GET  /governance/contracts/mission/{id}       → contracts for a mission
  GET  /governance/contracts/{id}               → single contract
  POST /governance/contracts/{id}/revoke        → revoke an active contract
  GET  /governance/contracts/{id}/eligibility   → deterministic eligibility check
  GET  /governance/analytics                    → lifecycle counters
  GET  /governance/inspect/{mission_id}         → full inspector for a mission

Governance Layer does NOT execute. Records human intent and eligibility only.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.governance import registry as reg
from app.governance import analytics as anal
from app.governance import timeline as tl
from app.governance import inspector as insp_module
from app.governance import eligibility as elig
from app.governance.models import ContractStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/governance", tags=["governance"])


class _RevokeBody(BaseModel):
    reason: str = ""


# ── GET /governance/contracts ─────────────────────────────────────────────────

@router.get("/contracts")
def list_contracts(
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
            st = ContractStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
        items = [c for c in items if c.status == st]

    return [c.to_dict() for c in items[:limit]]


# ── GET /governance/contracts/active ──────────────────────────────────────────

@router.get("/contracts/active")
def list_active(limit: int = Query(50, ge=1, le=500)):
    return [c.to_dict() for c in reg.list_active(limit=limit)]


# ── GET /governance/contracts/mission/{mission_id} ────────────────────────────

@router.get("/contracts/mission/{mission_id}")
def contracts_for_mission(mission_id: str, limit: int = Query(100, ge=1, le=500)):
    items = reg.list_for_mission(mission_id, limit=limit)
    return [c.to_dict() for c in items]


# ── GET /governance/analytics ─────────────────────────────────────────────────

@router.get("/analytics")
def get_analytics():
    return anal.get_analytics()


# ── GET /governance/inspect/{mission_id} ──────────────────────────────────────

@router.get("/inspect/{mission_id}")
def inspect_mission(mission_id: str):
    return insp_module.inspect(mission_id)


# ── GET /governance/contracts/{contract_id} ───────────────────────────────────

@router.get("/contracts/{contract_id}")
def get_contract(contract_id: str):
    item = reg.get(contract_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
    return item.to_dict()


# ── POST /governance/contracts/{contract_id}/revoke ───────────────────────────

@router.post("/contracts/{contract_id}/revoke")
def revoke_contract(contract_id: str, body: _RevokeBody = _RevokeBody()):
    item = reg.get(contract_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")
    if item.status != ContractStatus.active:
        raise HTTPException(status_code=409,
                            detail=f"Contract is {item.status.value}, not ACTIVE")

    age_ms = (time.time() - item.created_at) * 1000
    ok = reg.revoke(contract_id, reason=body.reason)
    if not ok:
        raise HTTPException(status_code=409, detail="Could not revoke contract")

    anal.record_revoked(age_ms)
    tl.record(contract_id, "revoked",
              mission_id  = item.mission_id or "",
              risk_level  = item.risk_level,
              source_type = item.source_type,
              approved    = item.approved)

    updated = reg.get(contract_id)
    return {
        "contract_id": contract_id,
        "status":      "REVOKED",
        "reason":      body.reason,
        "contract":    updated.to_dict() if updated else None,
    }


# ── GET /governance/contracts/{contract_id}/eligibility ───────────────────────

@router.get("/contracts/{contract_id}/eligibility")
def check_eligibility(contract_id: str):
    item = reg.get(contract_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")

    result = elig.check(item)
    auth   = result.to_authorization()
    return {
        "eligibility":           result.to_dict(),
        "execution_authorization": auth.to_dict(),
    }
