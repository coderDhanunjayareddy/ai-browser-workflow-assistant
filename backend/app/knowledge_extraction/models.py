from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.knowledge_extraction.research_spec import ResearchMissionSpec


@dataclass(frozen=True)
class PageReadArtifact:
    id: str
    title: str
    canonical_url: str
    headings: list[str]
    sections: list[dict[str, str]]
    paragraphs: list[str]
    metadata: dict[str, str]
    tables: list[list[dict[str, str]]]
    lists: list[list[str]]
    forms: list[dict[str, str]]
    pricing_blocks: list[str]
    contact_blocks: list[str]
    navigation_context: list[dict[str, str]]
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractionRecord:
    id: str
    source_page: str
    producing_action: str
    producing_phase: str
    extraction_type: str
    fields: dict[str, str]
    confidence: float
    validation: dict[str, Any]
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeArtifact:
    id: str
    artifact_type: Literal["comparison_table", "ranking", "summary", "bullets", "json", "csv", "markdown"]
    records: list[ExtractionRecord]
    content: dict[str, Any]
    validation: dict[str, Any]
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [record.to_dict() for record in self.records]
        return data


@dataclass(frozen=True)
class ReportArtifact:
    id: str
    format: Literal["markdown", "html", "json", "csv", "table", "object"]
    content: str
    structured: dict[str, Any]
    source_knowledge_id: str
    completion_status: Literal["pending", "complete", "failed"]
    timestamp_ms: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgePipelineTelemetry:
    page_read_ms: int
    extraction_ms: int
    synthesis_ms: int
    report_ms: int
    read_artifact_count: int
    extraction_record_count: int
    validation_failure_count: int
    duplicate_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgePipelineSnapshot:
    schema_version: str
    session_id: str
    current_phase: str | None
    required_fields: list[str]
    research_spec: ResearchMissionSpec | None
    read_artifacts: list[PageReadArtifact]
    extraction_records: list[ExtractionRecord]
    knowledge_artifact: KnowledgeArtifact | None
    report_artifact: ReportArtifact | None
    missing_artifacts: list[str]
    completion_status: dict[str, bool]
    telemetry: KnowledgePipelineTelemetry
    replay: list[dict[str, Any]] = field(default_factory=list)

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "current_phase": self.current_phase,
            "required_fields": self.required_fields,
            "research_spec": self.research_spec.to_dict() if self.research_spec else None,
            "record_count": len(self.extraction_records),
            "read_count": len(self.read_artifacts),
            "knowledge_artifact_id": self.knowledge_artifact.id if self.knowledge_artifact else None,
            "report_artifact_id": self.report_artifact.id if self.report_artifact else None,
            "missing_artifacts": self.missing_artifacts,
            "completion_status": self.completion_status,
            "records_preview": [
                {"source": record.source_page, "type": record.extraction_type, "fields": record.fields}
                for record in self.extraction_records[-8:]
            ],
        }
