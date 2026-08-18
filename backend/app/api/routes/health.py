import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.database import get_db
from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "ok",
        "db": db_status,
        "runtime": {
            "service": "ai-browser-assist-backend",
            "app_version": settings.app_version,
            "build_commit": settings.build_commit,
            "build_id": settings.build_id,
            "canonical_backend_url": settings.canonical_backend_url.rstrip("/"),
            "process_id": os.getpid(),
        },
    }
