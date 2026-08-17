from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.evaluation.production import (
    CapabilityGate,
    DisposableAccount,
    LiveEvaluationEvidence,
    RolloutStage,
    production_evidence_store,
)
from app.evaluation.red_team import run_live_policy_red_team
from app.evaluation.scaffold_retirement import build_retirement_register


router = APIRouter(prefix="/production-evidence", tags=["production-evidence"])


class RegisterAccountRequest(BaseModel):
    alias: str
    provider: str
    allowed_origins: list[str]
    persona: str = "synthetic"
    metadata: dict = Field(default_factory=dict)
    expires_at: datetime


class GateRequest(BaseModel):
    requested_stage: RolloutStage


class ReleaseAccountRequest(BaseModel):
    quarantine: bool = False


@router.post("/accounts")
def register_account(body: RegisterAccountRequest):
    try:
        return production_evidence_store.register_account(DisposableAccount(**body.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/lease")
def lease_account(account_id: str):
    try:
        return production_evidence_store.lease_account(account_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/accounts/{account_id}/release")
def release_account(account_id: str, body: ReleaseAccountRequest):
    try:
        return production_evidence_store.release_account(account_id, quarantine=body.quarantine)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/accounts")
def list_accounts():
    return production_evidence_store.accounts()


@router.post("/evaluations")
def record_evaluation(evidence: LiveEvaluationEvidence):
    try:
        return production_evidence_store.record(evidence)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/gates/{capability}")
def configure_gate(capability: str, gate: CapabilityGate):
    if capability != gate.capability:
        raise HTTPException(status_code=400, detail="capability path and body must match")
    return production_evidence_store.configure_gate(gate)


@router.post("/gates/{capability}/evaluate")
def evaluate_gate(capability: str, body: GateRequest):
    return production_evidence_store.evaluate_gate(capability, body.requested_stage)


@router.post("/red-team/run")
def run_red_team():
    return production_evidence_store.record_red_team_run(run_live_policy_red_team())


@router.get("/scaffolding/retirement-register")
def retirement_register():
    path = Path(__file__).resolve().parents[4] / "docs" / "phase0" / "runtime-inventory.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail="Phase 0 runtime inventory is unavailable")
    return build_retirement_register(path)


@router.get("/summary")
def evidence_summary():
    return production_evidence_store.summary()
