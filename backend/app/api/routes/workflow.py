from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.history import HistoryResponse
from app.schemas.workflow import LogEventRequest, LogEventResponse
from app.services import workflow_service
from app.budget_engine import BudgetExceededError
from app.services.analytics_service import get_analytics
from app.schemas.analytics import WorkflowAnalytics

router = APIRouter()


@router.post("/workflow/log", response_model=LogEventResponse, status_code=201)
def log_event(request: LogEventRequest, db: Session = Depends(get_db)) -> LogEventResponse:
    """
    Log an approval, rejection, or execution event for an action.
    Creates the parent session row automatically if it does not exist.
    """
    try:
        return workflow_service.log_event(db, request)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=409,
            detail={"status": "BUDGET_EXCEEDED", "reason": exc.reason},
        ) from exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to log event: {str(e)}")


@router.get("/workflow/history", response_model=HistoryResponse)
def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> HistoryResponse:
    """
    Return the most recent workflow sessions with all logged events.
    """
    try:
        return workflow_service.get_history(db, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@router.get("/workflow/{session_id}/analytics", response_model=WorkflowAnalytics)
def workflow_analytics(session_id: str, db: Session = Depends(get_db)) -> WorkflowAnalytics:
    try:
        return get_analytics(db, session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
