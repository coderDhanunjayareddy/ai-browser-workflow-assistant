from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.assist import AssistRequest, AssistResponse
from app.assist.ambient_assistant import run
from app.services.ai_service import AIProviderError, TransientAIError, is_transient_error
from app.budget_engine import BudgetExceededError

router = APIRouter()


@router.post("/assist", response_model=AssistResponse, status_code=200)
def assist(request: AssistRequest, db: Session = Depends(get_db)) -> AssistResponse:
    try:
        return run(request, db=db)
    except BudgetExceededError as exc:
        raise HTTPException(
            status_code=409,
            detail={"status": "BUDGET_EXCEEDED", "reason": exc.reason},
        ) from exc
    except AIProviderError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.provider} API error: {str(exc)}",
        ) from exc
    except TransientAIError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"AI service unavailable. Retry in a moment. Details: {str(exc)}",
        ) from exc
    except Exception as exc:
        if is_transient_error(exc):
            raise HTTPException(
                status_code=503,
                detail=f"AI service connection interrupted. Retry. Details: {str(exc)}",
            ) from exc
        raise HTTPException(status_code=500, detail=f"Assist failed: {str(exc)}") from exc
