"""
Phase B — Execution Gateway V1 — REST API routes.

Endpoints:
  POST /gateway/start/{plan_id}        → start an execution from a READY plan
  POST /gateway/pause/{execution_id}   → pause a pending/running execution
  POST /gateway/resume/{execution_id}  → resume a paused/pending execution
  POST /gateway/abort/{execution_id}   → abort (rollback-simulated) an execution
  GET  /gateway/status/{execution_id}  → current execution record
  GET  /gateway/history/{execution_id} → audit trail for an execution
  GET  /gateway/analytics              → gateway analytics
  GET  /gateway/inspect/{execution_id} → full inspector

The gateway ONLY orchestrates. The V1 adapter is a deterministic mock — no browser.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.execution_gateway import engine as gateway
from app.execution_gateway import registry as exec_registry
from app.execution_gateway import analytics as gw_analytics
from app.execution_gateway import audit as audit_trail
from app.execution_gateway import inspector as insp_module
from app.execution_gateway.engine import GatewayError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gateway", tags=["execution-gateway"])


# ── POST /gateway/start/{plan_id} ─────────────────────────────────────────────

@router.post("/start/{plan_id}")
def start_execution(plan_id: str, auto_run: bool = Query(True)):
    try:
        record = gateway.start(plan_id, auto_run=auto_run)
    except GatewayError as e:
        detail = {"message": e.message, "preflight": e.preflight} if e.preflight else e.message
        raise HTTPException(status_code=e.status_code, detail=detail)
    return record.to_dict()


# ── POST /gateway/pause/{execution_id} ────────────────────────────────────────

@router.post("/pause/{execution_id}")
def pause_execution(execution_id: str):
    try:
        return gateway.pause(execution_id).to_dict()
    except GatewayError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ── POST /gateway/resume/{execution_id} ───────────────────────────────────────

@router.post("/resume/{execution_id}")
def resume_execution(execution_id: str):
    try:
        return gateway.resume(execution_id).to_dict()
    except GatewayError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ── POST /gateway/abort/{execution_id} ────────────────────────────────────────

@router.post("/abort/{execution_id}")
def abort_execution(execution_id: str):
    try:
        return gateway.abort(execution_id).to_dict()
    except GatewayError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ── GET /gateway/analytics ────────────────────────────────────────────────────

@router.get("/analytics")
def get_analytics():
    return gw_analytics.get_analytics()


# ── GET /gateway/status/{execution_id} ────────────────────────────────────────

@router.get("/status/{execution_id}")
def get_status(execution_id: str):
    record = exec_registry.get(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return record.to_dict()


# ── GET /gateway/history/{execution_id} ───────────────────────────────────────

@router.get("/history/{execution_id}")
def get_history(execution_id: str, limit: int = Query(200, ge=1, le=500)):
    record = exec_registry.get(execution_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return {
        "execution_id": execution_id,
        "audit_trail":  [e.to_dict() for e in audit_trail.entries_for_execution(execution_id, limit=limit)],
        "step_executions": [s.to_dict() for s in record.step_executions],
        "rollback_history": record.rollback_history,
    }


# ── GET /gateway/inspect/{execution_id} ───────────────────────────────────────

@router.get("/inspect/{execution_id}")
def inspect_execution(execution_id: str):
    result = insp_module.inspect(execution_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
    return result


# ── Phase C additive endpoints (non-breaking) ─────────────────────────────────
# GET /gateway/browser/session/{execution_id}    → live browser session info
# GET /gateway/browser/screenshot/{execution_id} → latest screenshot (PNG file)

@router.get("/browser/session/{execution_id}")
def get_browser_session(execution_id: str):
    from app.execution_gateway.browser import session as browser_session
    from app.execution_gateway.browser import capabilities as browser_caps
    info = browser_session.session_info(execution_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"No browser session for {execution_id}")
    return {"session": info, "capabilities": browser_caps.get_capabilities()}


@router.get("/browser/screenshot/{execution_id}")
def get_browser_screenshot(execution_id: str):
    import os
    from fastapi.responses import FileResponse
    from app.execution_gateway.browser import session as browser_session
    s = browser_session.get(execution_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"No browser session for {execution_id}")
    path = s.latest_screenshot() or s.screenshot("api")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No screenshot available")
    return FileResponse(path, media_type="image/png")
