from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.policy.live_engine import live_policy_engine
from app.policy.live_store import live_policy_store
from app.policy.models import LivePolicyRequest


router = APIRouter(prefix="/policy", tags=["policy"])


class ConfirmationRequest(BaseModel):
    request: LivePolicyRequest
    ttl_seconds: int = Field(default=120, ge=1, le=300)
    confirmation_source: str = Field(default="human_sidepanel", pattern=r"^human(?:_[a-z0-9_-]+)?$")


class OriginGrantRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    origin: str = Field(min_length=1, max_length=2048)
    action_types: list[str] = Field(min_length=1, max_length=50)
    ttl_seconds: int = Field(default=900, ge=1, le=3600)
    grant_source: str = Field(default="human_sidepanel", pattern=r"^human(?:_[a-z0-9_-]+)?$")


@router.post("/evaluate")
def evaluate_policy(request: LivePolicyRequest):
    try:
        return live_policy_engine.evaluate(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm")
def confirm_action(body: ConfirmationRequest):
    try:
        return live_policy_engine.issue_confirmation(body.request, ttl_seconds=body.ttl_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/enforce")
def enforce_policy(request: LivePolicyRequest):
    try:
        return live_policy_engine.enforce(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/origin-grants")
def create_origin_grant(body: OriginGrantRequest):
    try:
        return live_policy_engine.issue_origin_grant(
            session_id=body.session_id,
            origin=body.origin,
            action_types=body.action_types,
            ttl_seconds=body.ttl_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/origin-grants/{grant_id}/revoke")
def revoke_origin_grant(grant_id: str):
    try:
        return live_policy_engine.revoke_origin_grant(grant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/audit/{session_id}")
def get_policy_audit(session_id: str, limit: int = Query(default=200, ge=1, le=1000)):
    return live_policy_store.audit_for_session(session_id, limit=limit)
