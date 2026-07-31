from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.db import ValidationBenchmarkRunRecord
from app.validation.benchmark_models import BenchmarkRunResult


class BenchmarkRepository(ABC):
    @abstractmethod
    def save(self, result: BenchmarkRunResult) -> BenchmarkRunResult:
        raise NotImplementedError

    @abstractmethod
    def list_runs(self) -> list[BenchmarkRunResult]:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> BenchmarkRunResult | None:
        raise NotImplementedError


class SqlAlchemyBenchmarkRepository(BenchmarkRepository):
    def __init__(self, db: Session):
        self.db = db

    def save(self, result: BenchmarkRunResult) -> BenchmarkRunResult:
        self.db.merge(
            ValidationBenchmarkRunRecord(
                run_id=result.run_id,
                benchmark_id=result.benchmark_id,
                mission_id=result.mission_id,
                category=result.category,
                status=result.status,
                score=result.score,
                metrics=dict(result.metrics),
                diagnostics=dict(result.diagnostics),
                report=dict(result.report),
                created_at=result.timestamp,
            )
        )
        self.db.commit()
        return result

    def list_runs(self) -> list[BenchmarkRunResult]:
        records = self.db.query(ValidationBenchmarkRunRecord).order_by(ValidationBenchmarkRunRecord.created_at.asc()).all()
        return [_from_record(record) for record in records]

    def get_run(self, run_id: str) -> BenchmarkRunResult | None:
        record = self.db.get(ValidationBenchmarkRunRecord, run_id)
        return _from_record(record) if record is not None else None


def _from_record(record: ValidationBenchmarkRunRecord) -> BenchmarkRunResult:
    return BenchmarkRunResult(
        run_id=record.run_id,
        benchmark_id=record.benchmark_id,
        category=record.category,
        mission_id=record.mission_id,
        status=record.status,
        score=float(record.score or 0.0),
        metrics=dict(record.metrics or {}),
        diagnostics=dict(record.diagnostics or {}),
        report=dict(record.report or {}),
        timestamp=_timestamp(record.created_at),
    )


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.now(UTC)
