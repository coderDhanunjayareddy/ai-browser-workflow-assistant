from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.benchmark.benchmark_controller import BenchmarkController
from app.benchmark.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.benchmark.benchmark_service import BenchmarkService
from app.core.database import get_db
from app.feature_flags import is_shadow_or_active


router = APIRouter(prefix="/benchmarks", tags=["execution-benchmark-v1"])


@router.get("")
def benchmarks(db: Session = Depends(get_db)) -> dict:
    return {"benchmarks": _controller_or_disabled(db).catalog()}


@router.get("/catalog")
def catalog(db: Session = Depends(get_db)) -> dict:
    return {"benchmarks": _controller_or_disabled(db).catalog()}


@router.get("/run/{run_id}")
def run(run_id: str, db: Session = Depends(get_db)) -> dict:
    result = _controller_or_disabled(db).run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Benchmark run {run_id!r} not found")
    return result.to_dict()


@router.get("/report/{run_id}")
def report(run_id: str, db: Session = Depends(get_db)) -> dict:
    result = _controller_or_disabled(db).report(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Benchmark report for run {run_id!r} not found")
    return result


@router.get("/failures/{run_id}")
def failures(run_id: str, db: Session = Depends(get_db)) -> dict:
    return {"run_id": run_id, "failures": _controller_or_disabled(db).failures(run_id)}


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)) -> dict:
    return {"metrics": _controller_or_disabled(db).metrics()}


@router.get("/history")
def history(db: Session = Depends(get_db)) -> dict:
    return {"runs": _controller_or_disabled(db).history()}


@router.get("/trends")
def trends(db: Session = Depends(get_db)) -> dict:
    return _controller_or_disabled(db).trends()


@router.get("/export")
def export(db: Session = Depends(get_db)) -> dict:
    return _controller_or_disabled(db).export()


def _controller_or_disabled(db: Session) -> BenchmarkController:
    if not is_shadow_or_active("EXECUTION_BENCHMARK_V1"):
        raise HTTPException(status_code=404, detail="EXECUTION_BENCHMARK_V1 is disabled")
    return BenchmarkController(BenchmarkService(SqlAlchemyBenchmarkRepository(db)))
