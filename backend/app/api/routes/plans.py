"""
V9.0 Execution Planning Layer — REST API routes.

Endpoints (literal routes before parameterized):
  POST /plans/create/{authorization_id}  → build a plan from an ExecutionAuthorization
  POST /plans/validate/{plan_id}         → validate a plan → READY when valid
  POST /plans/{plan_id}/archive          → archive (ABORTED) a plan
  GET  /plans                            → list plans (filter: status, mission_id)
  GET  /plans/analytics                  → plan analytics
  GET  /plans/mission/{mission_id}       → plans for a mission
  GET  /plans/task/{task_id}             → plans for a task
  GET  /plans/inspect/{plan_id}          → full inspector
  GET  /plans/{plan_id}                  → single plan by id

This layer performs NO browser execution. It only produces / validates plans.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.execution_planning import registry as reg
from app.execution_planning import planner as planner_module
from app.execution_planning import validator as validator_module
from app.execution_planning import analytics as anal
from app.execution_planning import timeline as tl
from app.execution_planning import inspector as insp_module
from app.execution_planning.models import PlanStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/plans", tags=["execution-planning"])


# ── POST /plans/create/{authorization_id} ─────────────────────────────────────

@router.post("/create/{authorization_id}")
def create_plan(authorization_id: str):
    from app.authorization import registry as auth_reg
    auth = auth_reg.get(authorization_id)
    if auth is None:
        raise HTTPException(status_code=404, detail=f"Authorization {authorization_id} not found")
    if not auth.authorized:
        raise HTTPException(
            status_code=409,
            detail=f"Authorization {authorization_id} is not authorized (status={auth.status.value})"
        )

    # Gather optional planning context (non-blocking).
    mission = None
    try:
        if auth.mission_id:
            from app.mission import store as ms
            mission = ms.get(auth.mission_id)
    except Exception:
        pass

    runtime_context = None
    try:
        if auth.mission_id:
            from app.runtime import registry as rt_reg
            from app.runtime import cache as rt_cache
            sessions = rt_reg.list_for_mission(auth.mission_id, limit=1)
            if sessions:
                runtime_context = rt_cache.peek(sessions[0].runtime_id)
    except Exception:
        pass

    plan = planner_module.create_plan(auth, mission=mission, runtime_context=runtime_context)
    reg.add(plan)
    anal.record_created(plan.estimated_steps, plan.estimated_duration_ms, plan.rollback_supported)
    tl.record(plan.plan_id, "created",
              mission_id=plan.mission_id or "",
              authorization_id=plan.authorization_id,
              status=plan.status.value)
    return plan.to_dict()


# ── POST /plans/validate/{plan_id} ────────────────────────────────────────────

@router.post("/validate/{plan_id}")
def validate_plan(plan_id: str):
    plan = reg.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")

    result = validator_module.validate(plan)
    anal.record_validated(result.valid)
    tl.record(plan_id, "validated", mission_id=plan.mission_id or "",
              authorization_id=plan.authorization_id, status=plan.status.value)

    if result.valid:
        reg.set_status(plan_id, PlanStatus.ready)
        reg.mark_validated(plan_id, result.validated_at)
        tl.record(plan_id, "ready", mission_id=plan.mission_id or "",
                  authorization_id=plan.authorization_id, status=PlanStatus.ready.value)

    out = result.to_dict()
    out["plan_status"] = reg.get(plan_id).status.value
    return out


# ── POST /plans/{plan_id}/archive ─────────────────────────────────────────────

@router.post("/{plan_id}/archive")
def archive_plan(plan_id: str):
    plan = reg.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    ok = reg.archive(plan_id, time.time())
    if not ok:
        raise HTTPException(status_code=409, detail=f"Plan {plan_id} already archived")
    anal.record_archived()
    tl.record(plan_id, "archived", mission_id=plan.mission_id or "",
              authorization_id=plan.authorization_id, status=PlanStatus.aborted.value)
    return {"plan_id": plan_id, "status": PlanStatus.aborted.value}


# ── GET /plans ────────────────────────────────────────────────────────────────

@router.get("")
def list_plans(
    status:     Optional[str] = Query(None),
    mission_id: Optional[str] = Query(None),
    limit:      int           = Query(50, ge=1, le=500),
):
    if mission_id:
        plans = reg.list_for_mission(mission_id, limit=limit)
    else:
        plans = reg.list_all(limit=limit)

    if status:
        try:
            st = PlanStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown plan status: {status}")
        plans = [p for p in plans if p.status == st]

    return [p.to_dict(include_steps=False) for p in plans[:limit]]


# ── GET /plans/analytics ──────────────────────────────────────────────────────

@router.get("/analytics")
def get_analytics():
    return anal.get_analytics()


# ── GET /plans/mission/{mission_id} ───────────────────────────────────────────

@router.get("/mission/{mission_id}")
def plans_for_mission(mission_id: str, limit: int = Query(100, ge=1, le=500)):
    plans = reg.list_for_mission(mission_id, limit=limit)
    return [p.to_dict(include_steps=False) for p in plans]


# ── GET /plans/task/{task_id} ─────────────────────────────────────────────────

@router.get("/task/{task_id}")
def plans_for_task(task_id: str, limit: int = Query(100, ge=1, le=500)):
    plans = reg.list_for_task(task_id, limit=limit)
    return [p.to_dict(include_steps=False) for p in plans]


# ── GET /plans/inspect/{plan_id} ──────────────────────────────────────────────

@router.get("/inspect/{plan_id}")
def inspect_plan(plan_id: str):
    result = insp_module.inspect(plan_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return result


# ── GET /plans/{plan_id} ──────────────────────────────────────────────────────

@router.get("/{plan_id}")
def get_plan(plan_id: str):
    plan = reg.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    return plan.to_dict()
