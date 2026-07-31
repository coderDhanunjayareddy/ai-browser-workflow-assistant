from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.feature_flags import is_shadow_or_active
from app.validation.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.validation.validation_controller import ValidationController
from app.validation.validation_service import ValidationService


router = APIRouter(prefix="/validation", tags=["cognitive-runtime-validation"])


@router.get("/benchmarks")
def get_validation_benchmarks(db: Session = Depends(get_db)) -> dict:
    return {"benchmarks": _controller_or_disabled(db).benchmarks()}


@router.get("/benchmark/{benchmark_id}")
def get_validation_benchmark(benchmark_id: str, db: Session = Depends(get_db)) -> dict:
    benchmark = _controller_or_disabled(db).benchmark(benchmark_id)
    if benchmark is None:
        raise HTTPException(status_code=404, detail=f"Benchmark {benchmark_id!r} not found")
    return benchmark


@router.get("/report")
def get_validation_report(db: Session = Depends(get_db)) -> dict:
    return _controller_or_disabled(db).report()


@router.get("/metrics")
def get_validation_metrics(db: Session = Depends(get_db)) -> dict:
    return {"metrics": _controller_or_disabled(db).metrics()}


@router.get("/diagnostics")
def get_validation_diagnostics(db: Session = Depends(get_db)) -> dict:
    return _controller_or_disabled(db).diagnostics()


@router.get("/migration")
def get_validation_migration(db: Session = Depends(get_db)) -> dict:
    return {"migration_readiness": _controller_or_disabled(db).migration()}


@router.get("/readiness")
def get_validation_readiness(db: Session = Depends(get_db)) -> dict:
    return _controller_or_disabled(db).readiness()


@router.get("/quality")
def get_validation_quality(db: Session = Depends(get_db)) -> dict:
    return _controller_or_disabled(db).quality()


def _controller_or_disabled(db: Session) -> ValidationController:
    if not is_shadow_or_active("COGNITIVE_RUNTIME_V2"):
        raise HTTPException(status_code=404, detail="COGNITIVE_RUNTIME_V2 is disabled")
    return ValidationController(ValidationService(SqlAlchemyBenchmarkRepository(db)))
