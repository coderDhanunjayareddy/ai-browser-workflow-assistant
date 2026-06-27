"""
V8.8 Execution Authorization Framework — REST API routes.

Endpoints (literal routes before parameterized):
  GET  /authorization                         → list all authorizations
  GET  /authorization/analytics               → lifecycle counters
  GET  /authorization/contract/{contract_id}  → latest auth for a contract
  GET  /authorization/mission/{mission_id}    → authorizations for a mission
  GET  /authorization/readiness/{mission_id}  → readiness report
  GET  /authorization/inspect/{mission_id}    → full inspector
  GET  /authorization/{id}                    → single authorization by ID
  POST /authorization/evaluate/{contract_id}  → evaluate contract → new authorization

Execution Authorization Framework does NOT execute. Records authorization decisions only.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.authorization import registry as reg
from app.authorization import analytics as anal
from app.authorization import timeline as tl
from app.authorization import inspector as insp_module
from app.authorization import engine as auth_engine
from app.authorization import readiness as rdns_module
from app.authorization.models import AuthorizationStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/authorization", tags=["authorization"])


# ── GET /authorization ────────────────────────────────────────────────────────

@router.get("")
def list_authorizations(
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
            st = AuthorizationStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status: {status}")
        items = [a for a in items if a.status == st]

    return [a.to_dict() for a in items[:limit]]


# ── GET /authorization/analytics ──────────────────────────────────────────────

@router.get("/analytics")
def get_analytics():
    return anal.get_analytics()


# ── GET /authorization/contract/{contract_id} ─────────────────────────────────

@router.get("/contract/{contract_id}")
def get_for_contract(contract_id: str):
    item = reg.get_for_contract(contract_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"No authorization found for contract {contract_id}"
        )
    return item.to_dict()


# ── GET /authorization/mission/{mission_id} ───────────────────────────────────

@router.get("/mission/{mission_id}")
def authorizations_for_mission(mission_id: str, limit: int = Query(100, ge=1, le=500)):
    items = reg.list_for_mission(mission_id, limit=limit)
    return [a.to_dict() for a in items]


# ── GET /authorization/readiness/{mission_id} ─────────────────────────────────

@router.get("/readiness/{mission_id}")
def readiness_report(mission_id: str):
    report = rdns_module.evaluate(mission_id)
    return report.to_dict()


# ── GET /authorization/inspect/{mission_id} ───────────────────────────────────

@router.get("/inspect/{mission_id}")
def inspect_mission(mission_id: str):
    return insp_module.inspect(mission_id)


# ── POST /authorization/evaluate/{contract_id} ────────────────────────────────

@router.post("/evaluate/{contract_id}")
def evaluate_contract(contract_id: str):
    from app.governance import registry as gov_reg
    contract = gov_reg.get(contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id} not found")

    # Enrich with trust score (non-blocking)
    trust_score:  Optional[float] = None
    mission_state: Optional[str]  = None
    try:
        if contract.mission_id:
            from app.trust import mission_analyzer as ma
            ev = ma.analyze(contract.mission_id)
            trust_score = ev.trust_score
    except Exception:
        pass
    try:
        if contract.mission_id:
            from app.mission import store as ms
            m = ms.get(contract.mission_id)
            if m:
                mission_state = m.state.value
    except Exception:
        pass

    t0   = time.perf_counter()
    auth = auth_engine.evaluate(contract, mission_state=mission_state, trust_score=trust_score)
    eval_ms = (time.perf_counter() - t0) * 1000

    reg.add(auth)
    anal.record_created(auth.authorized, eval_ms=eval_ms)
    event = "approved" if auth.authorized else "denied"
    tl.record(
        auth.authorization_id, event,
        mission_id   = auth.mission_id or "",
        risk_level   = auth.risk_level,
        contract_id  = contract_id,
        authorized   = auth.authorized,
    )

    return {
        "authorization_id": auth.authorization_id,
        "contract_id":      contract_id,
        "authorized":       auth.authorized,
        "status":           auth.status.value,
        "eval_ms":          round(eval_ms, 3),
        "authorization":    auth.to_dict(),
    }


# ── GET /authorization/{id} ───────────────────────────────────────────────────

@router.get("/{authorization_id}")
def get_authorization(authorization_id: str):
    item = reg.get(authorization_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"Authorization {authorization_id} not found"
        )
    return item.to_dict()
