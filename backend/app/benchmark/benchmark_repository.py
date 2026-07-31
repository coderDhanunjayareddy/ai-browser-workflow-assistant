from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.benchmark.benchmark_models import BenchmarkReport, BenchmarkRunResult, ExecutionTrace, FailureClassification
from app.models.db import (
    BenchmarkExecutionTraceRecord,
    BenchmarkFailureRecord,
    BenchmarkMetricRecord,
    BenchmarkReportRecord,
    BenchmarkRunRecord,
)


class BenchmarkRepository(ABC):
    @abstractmethod
    def save(self, result: BenchmarkRunResult) -> BenchmarkRunResult:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> BenchmarkRunResult | None:
        raise NotImplementedError

    @abstractmethod
    def list_runs(self) -> list[BenchmarkRunResult]:
        raise NotImplementedError

    @abstractmethod
    def reports(self, run_id: str) -> list[BenchmarkReport]:
        raise NotImplementedError

    @abstractmethod
    def failures(self, run_id: str) -> list[FailureClassification]:
        raise NotImplementedError


class SqlAlchemyBenchmarkRepository(BenchmarkRepository):
    def __init__(self, db: Session):
        self.db = db

    def save(self, result: BenchmarkRunResult) -> BenchmarkRunResult:
        self.db.merge(BenchmarkRunRecord(
            run_id=result.run_id,
            benchmark_id=result.benchmark_id,
            mission_id=result.mission_id,
            category=result.category,
            status=result.status,
            score=result.score,
            duration_ms=result.duration_ms,
            run_metadata=dict(result.metadata),
            created_at=result.timestamp,
        ))
        self.db.merge(BenchmarkExecutionTraceRecord(
            trace_id=result.trace.trace_id,
            run_id=result.run_id,
            mission_id=result.mission_id,
            benchmark_id=result.benchmark_id,
            timeline=list(result.trace.timeline),
            snapshot=dict(result.trace.stages),
            created_at=result.trace.timestamp,
        ))
        self.db.merge(BenchmarkMetricRecord(
            metric_id=f"benchmark_metric_{result.run_id}",
            run_id=result.run_id,
            benchmark_id=result.benchmark_id,
            metrics=dict(result.metrics),
            created_at=result.timestamp,
        ))
        for failure in result.failures:
            self.db.merge(BenchmarkFailureRecord(
                failure_id=failure.failure_id,
                run_id=result.run_id,
                benchmark_id=result.benchmark_id,
                category=failure.category,
                root_cause=failure.root_cause,
                affected_subsystem=failure.affected_subsystem,
                timeline=list(failure.timeline),
                recommended_fix=failure.recommended_fix,
                confidence=failure.confidence,
                created_at=result.timestamp,
            ))
        for report in result.reports:
            self.db.merge(BenchmarkReportRecord(
                report_id=report.report_id,
                run_id=result.run_id,
                report_type=report.report_type,
                json_report=dict(report.json_report),
                markdown_report=report.markdown_report,
                created_at=report.timestamp,
            ))
        self.db.commit()
        return result

    def get_run(self, run_id: str) -> BenchmarkRunResult | None:
        record = self.db.get(BenchmarkRunRecord, run_id)
        return self._run_from_record(record) if record is not None else None

    def list_runs(self) -> list[BenchmarkRunResult]:
        records = self.db.query(BenchmarkRunRecord).order_by(BenchmarkRunRecord.created_at.asc()).all()
        return [self._run_from_record(record) for record in records]

    def reports(self, run_id: str) -> list[BenchmarkReport]:
        records = self.db.query(BenchmarkReportRecord).filter(BenchmarkReportRecord.run_id == run_id).order_by(BenchmarkReportRecord.created_at.asc()).all()
        return [_report_from_record(record) for record in records]

    def failures(self, run_id: str) -> list[FailureClassification]:
        records = self.db.query(BenchmarkFailureRecord).filter(BenchmarkFailureRecord.run_id == run_id).order_by(BenchmarkFailureRecord.created_at.asc()).all()
        return [_failure_from_record(record) for record in records]

    def _run_from_record(self, record: BenchmarkRunRecord) -> BenchmarkRunResult:
        trace_record = self.db.query(BenchmarkExecutionTraceRecord).filter(BenchmarkExecutionTraceRecord.run_id == record.run_id).first()
        metric_record = self.db.query(BenchmarkMetricRecord).filter(BenchmarkMetricRecord.run_id == record.run_id).first()
        trace = ExecutionTrace(
            trace_id=trace_record.trace_id if trace_record else f"benchmark_trace_{record.run_id}",
            benchmark_id=record.benchmark_id,
            mission_id=record.mission_id,
            stages=dict(trace_record.snapshot or {}) if trace_record else {},
            timeline=list(trace_record.timeline or []) if trace_record else [],
            timestamp=_timestamp(trace_record.created_at if trace_record else record.created_at),
        )
        return BenchmarkRunResult(
            run_id=record.run_id,
            benchmark_id=record.benchmark_id,
            mission_id=record.mission_id,
            category=record.category,
            status=record.status,
            score=float(record.score or 0.0),
            metrics=dict(metric_record.metrics or {}) if metric_record else {},
            trace=trace,
            failures=self.failures(record.run_id),
            reports=self.reports(record.run_id),
            duration_ms=int(record.duration_ms or 0),
            metadata=dict(record.run_metadata or {}),
            timestamp=_timestamp(record.created_at),
        )


def _report_from_record(record: BenchmarkReportRecord) -> BenchmarkReport:
    return BenchmarkReport(
        report_id=record.report_id,
        run_id=record.run_id,
        benchmark_id=str((record.json_report or {}).get("mission_report", {}).get("benchmark_id") or ""),
        report_type=record.report_type,
        json_report=dict(record.json_report or {}),
        markdown_report=record.markdown_report or "",
        timestamp=_timestamp(record.created_at),
    )


def _failure_from_record(record: BenchmarkFailureRecord) -> FailureClassification:
    return FailureClassification(
        failure_id=record.failure_id,
        category=record.category,
        root_cause=record.root_cause,
        affected_subsystem=record.affected_subsystem,
        timeline=list(record.timeline or []),
        recommended_fix=record.recommended_fix,
        confidence=float(record.confidence or 0.0),
    )


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.now(UTC)
