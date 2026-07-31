from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class BenchmarkCategory(str, Enum):
    RESEARCH = "research"
    SHOPPING = "shopping"
    BOOKING = "booking"
    AUTHENTICATION = "authentication"
    NAVIGATION = "navigation"
    FORMS = "forms"
    JOB_APPLICATIONS = "job_applications"
    DASHBOARD_WORKFLOWS = "dashboard_workflows"
    MULTI_TAB_RESEARCH = "multi_tab_research"
    EXTRACTION = "extraction"
    UPLOAD = "upload"
    DOWNLOAD = "download"
    EMAIL = "email"
    CALENDAR = "calendar"
    CROSS_SYSTEM_WORKFLOW = "cross_system_workflow"
    CUSTOM_MISSION = "custom_mission"


@dataclass(frozen=True)
class BenchmarkDefinition:
    benchmark_id: str
    category: str
    mission: str
    expected_outcome: str
    expected_success_criteria: list[str]
    expected_providers: list[str]
    expected_blueprint_structure: list[str]
    expected_ledger_progression: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkRunInput:
    benchmark: BenchmarkDefinition
    mission_id: str | None = None
    runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    cognitive_snapshot: dict[str, Any] = field(default_factory=dict)
    comparison_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkRunResult:
    benchmark_id: str
    category: str
    mission_id: str | None
    status: str
    score: float
    metrics: dict[str, Any]
    diagnostics: dict[str, Any]
    report: dict[str, Any]
    run_id: str = field(default_factory=lambda: f"validation_run_{uuid.uuid4().hex}")
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkRunResult":
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except ValueError:
                timestamp = datetime.now(UTC)
        if not isinstance(timestamp, datetime):
            timestamp = datetime.now(UTC)
        return cls(
            run_id=str(data.get("run_id") or f"validation_run_{uuid.uuid4().hex}"),
            benchmark_id=str(data.get("benchmark_id") or ""),
            category=str(data.get("category") or BenchmarkCategory.CUSTOM_MISSION.value),
            mission_id=data.get("mission_id"),
            status=str(data.get("status") or "evaluated"),
            score=float(data.get("score") or 0.0),
            metrics=dict(data.get("metrics") or {}),
            diagnostics=dict(data.get("diagnostics") or {}),
            report=dict(data.get("report") or {}),
            timestamp=timestamp,
        )
