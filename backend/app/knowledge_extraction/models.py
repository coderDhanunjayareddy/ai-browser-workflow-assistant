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
    pricing_plans: list[dict[str, str]] = field(default_factory=list)
    documentation_sections: list[dict[str, str]] = field(default_factory=list)
    job_postings: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FieldEvidence:
    field: str
    value: str
    source_url: str
    source_text: str
    source_kind: Literal["title", "heading", "paragraph", "section", "documentation_section", "pricing_block", "pricing_plan", "job_posting", "contact_block", "form", "url", "collection_item", "missing"]
    confidence: float
    missing_reason: str = ""

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
    field_evidence: dict[str, FieldEvidence] = field(default_factory=dict)
    entity_type: Literal["research_source", "pricing_plan", "documentation_page", "job_posting", "directory_entry", "form_result", "file_result", "generic"] = "generic"
    entity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["field_evidence"] = {
            name: evidence.to_dict() if hasattr(evidence, "to_dict") else evidence
            for name, evidence in self.field_evidence.items()
        }
        return data


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
    read_artifacts: list[PageReadArtifact]
    extraction_records: list[ExtractionRecord]
    knowledge_artifact: KnowledgeArtifact | None
    report_artifact: ReportArtifact | None
    missing_artifacts: list[str]
    completion_status: dict[str, bool]
    telemetry: KnowledgePipelineTelemetry
    replay: list[dict[str, Any]] = field(default_factory=list)
    research_spec: ResearchMissionSpec | None = None
    collection_state: Any | None = None

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
            "collection_state": self.collection_state.to_dict() if hasattr(self.collection_state, "to_dict") else self.collection_state,
            "records_preview": [
                {
                    "source": record.source_page,
                    "type": record.extraction_type,
                    "entity_type": record.entity_type,
                    "entity": record.entity,
                    "fields": record.fields,
                    "field_evidence": {
                        name: {
                            "source_kind": evidence.source_kind,
                            "confidence": evidence.confidence,
                            "missing_reason": evidence.missing_reason,
                        }
                        for name, evidence in list(record.field_evidence.items())[:8]
                    },
                }
                for record in self.extraction_records[-8:]
            ],
        }
