from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class BenchmarkCategory(str, Enum):
    RESEARCH = "research"
    SHOPPING = "shopping"
    NAVIGATION = "navigation"
    EXTRACTION = "extraction"
    FORMS = "forms"
    AUTHENTICATION = "authentication"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    DASHBOARD = "dashboard"
    DOCUMENTATION = "documentation"
    NEWS = "news"
    JOB_APPLICATION = "job_application"
    CROSS_SYSTEM = "cross_system"
    CUSTOM = "custom"


@dataclass(frozen=True)
class BenchmarkMission:
    id: str
    title: str
    description: str
    category: str
    difficulty: str
    user_prompt: str
    expected_deliverable: str
    expected_blueprint: list[str]
    expected_success_criteria: list[str]
    expected_providers: list[str]
    timeout: int
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionTrace:
    benchmark_id: str
    mission_id: str | None
    stages: dict[str, Any]
    timeline: list[dict[str, Any]]
    trace_id: str = field(default_factory=lambda: f"benchmark_trace_{uuid.uuid4().hex}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class FailureClassification:
    category: str
    root_cause: str
    affected_subsystem: str
    timeline: list[dict[str, Any]]
    recommended_fix: str
    confidence: float
    failure_id: str = field(default_factory=lambda: f"benchmark_failure_{uuid.uuid4().hex}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkReport:
    run_id: str
    benchmark_id: str
    json_report: dict[str, Any]
    markdown_report: str
    report_id: str = field(default_factory=lambda: f"benchmark_report_{uuid.uuid4().hex}")
    report_type: str = "benchmark"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(frozen=True)
class BenchmarkRunResult:
    benchmark_id: str
    category: str
    status: str
    score: float
    metrics: dict[str, Any]
    trace: ExecutionTrace
    failures: list[FailureClassification]
    reports: list[BenchmarkReport]
    mission_id: str | None = None
    run_id: str = field(default_factory=lambda: f"benchmark_run_{uuid.uuid4().hex}")
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["trace"] = self.trace.to_dict()
        data["failures"] = [failure.to_dict() for failure in self.failures]
        data["reports"] = [report.to_dict() for report in self.reports]
        return data
