from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.intent import IntentNextRequest, IntentNextResponse, IntentUpdateRequest, IntentUpdateResponse
from app.services import mission_ledger_service


router = APIRouter(prefix="/intent", tags=["intent-runtime"])


@router.post("/next", response_model=IntentNextResponse)
def next_intent(request: IntentNextRequest, db: Session = Depends(get_db)) -> IntentNextResponse:
    return mission_ledger_service.next_intent(
        db,
        mission_id=request.mission_id,
        provider=request.provider,
    )


@router.post("/update", response_model=IntentUpdateResponse)
def update_intent(request: IntentUpdateRequest, db: Session = Depends(get_db)) -> IntentUpdateResponse:
    try:
        return mission_ledger_service.update_intent(
            db,
            mission_id=request.mission_id,
            intent_id=request.intent_id,
            outcome=request.outcome,
            evidence=request.evidence,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
