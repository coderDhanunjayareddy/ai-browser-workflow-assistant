from __future__ import annotations

from app.knowledge_extraction.models import ExtractionRecord, KnowledgeArtifact, PageReadArtifact, ReportArtifact


def build_replay(
    reads: list[PageReadArtifact],
    records: list[ExtractionRecord],
    knowledge: KnowledgeArtifact | None,
    report: ReportArtifact | None,
) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for read in reads[-8:]:
        frames.append({"event": "knowledge.page_read", "id": read.id, "url": read.canonical_url, "paragraphs": len(read.paragraphs)})
    for record in records[-12:]:
        frames.append({"event": "knowledge.extracted", "id": record.id, "source": record.source_page, "valid": record.validation.get("valid")})
    if knowledge:
        frames.append({"event": "knowledge.synthesized", "id": knowledge.id, "type": knowledge.artifact_type})
    if report:
        frames.append({"event": "knowledge.report", "id": report.id, "format": report.format, "status": report.completion_status})
    return frames[-30:]
