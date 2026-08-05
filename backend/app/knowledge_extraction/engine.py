from __future__ import annotations

import time
from typing import Any

from app.feature_flags import is_active, is_shadow_or_active
from app.knowledge_extraction.extraction_engine import extract_records, required_fields_for_task
from app.knowledge_extraction.models import KnowledgePipelineSnapshot, KnowledgePipelineTelemetry
from app.knowledge_extraction.page_reader import read_page
from app.knowledge_extraction.research_spec import build_research_mission_spec
from app.knowledge_extraction.registry import ExtractionRegistry
from app.knowledge_extraction.replay import build_replay
from app.knowledge_extraction.report_engine import generate_report
from app.knowledge_extraction.synthesizer import synthesize_knowledge
from app.knowledge_extraction.validator import validate_records, validation_summary
from app.schemas.response import AnalyzeResponse


class KnowledgeExtractionPipeline:
    def __init__(self) -> None:
        self.registry = ExtractionRegistry()

    def observe(
        self,
        *,
        session_id: str,
        task: str,
        page_context: Any,
        current_phase: str | None = None,
    ) -> KnowledgePipelineSnapshot | None:
        if not _enabled():
            return None
        research_spec = build_research_mission_spec(task)
        required = research_spec.required_fields if research_spec else required_fields_for_task(task)
        read_started = time.perf_counter()
        read = read_page(page_context) if is_shadow_or_active("V50_PAGE_READER") else None
        read_ms = int((time.perf_counter() - read_started) * 1000)
        extraction_started = time.perf_counter()
        records = extract_records(read, task, current_phase, required_fields=required) if read and is_shadow_or_active("V50_EXTRACTION_ENGINE") else []
        extraction_ms = int((time.perf_counter() - extraction_started) * 1000)
        if is_shadow_or_active("V50_EXTRACTION_VALIDATION"):
            records = validate_records(records, required)
        reads, all_records, duplicates = self.registry.merge(session_id, read, records) if read else ([], self.registry.get_records(session_id), 0)
        if is_shadow_or_active("V50_EXTRACTION_VALIDATION"):
            all_records = validate_records(all_records, required)
        synthesis_started = time.perf_counter()
        knowledge = synthesize_knowledge(all_records, required, task, research_spec=research_spec) if is_shadow_or_active("V50_SYNTHESIS") else None
        synthesis_ms = int((time.perf_counter() - synthesis_started) * 1000)
        report_started = time.perf_counter()
        report = generate_report(knowledge, output_format=research_spec.output_format if research_spec else "markdown") if is_shadow_or_active("V50_REPORT_ENGINE") else None
        report_ms = int((time.perf_counter() - report_started) * 1000)
        validation = validation_summary(all_records)
        missing = _missing_artifacts(reads, all_records, knowledge, report, validation)
        telemetry = KnowledgePipelineTelemetry(
            page_read_ms=read_ms,
            extraction_ms=extraction_ms,
            synthesis_ms=synthesis_ms,
            report_ms=report_ms,
            read_artifact_count=len(reads),
            extraction_record_count=len(all_records),
            validation_failure_count=int(validation["failure_count"]),
            duplicate_count=duplicates,
        )
        return KnowledgePipelineSnapshot(
            schema_version="knowledge_extraction.v1",
            session_id=session_id,
            current_phase=current_phase,
            required_fields=required,
            research_spec=research_spec,
            read_artifacts=reads,
            extraction_records=all_records,
            knowledge_artifact=knowledge,
            report_artifact=report,
            missing_artifacts=missing,
            completion_status={
                "read": bool(reads),
                "extract": _records_satisfy_spec(all_records, validation, research_spec),
                "synthesize": knowledge is not None,
                "report": report is not None and report.completion_status == "complete",
                "source_count": _source_count_satisfied(all_records, research_spec),
            },
            telemetry=telemetry,
            replay=build_replay(reads, all_records, knowledge, report),
        )

    def enrich_context(self, compressed_context: dict[str, Any], snapshot: KnowledgePipelineSnapshot | None) -> dict[str, Any]:
        if snapshot is None or not _active():
            return compressed_context
        enriched = dict(compressed_context)
        enriched["knowledge_extraction"] = snapshot.to_compact_context()
        return enriched

    def postprocess_response(self, result: AnalyzeResponse, snapshot: KnowledgePipelineSnapshot | None) -> AnalyzeResponse:
        return result


def _missing_artifacts(reads: list[Any], records: list[Any], knowledge: Any, report: Any, validation: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not reads:
        missing.append("page_read")
    if not records:
        missing.append("extraction_records")
    if not validation.get("valid"):
        missing.append("validated_extraction_records")
    if knowledge is None:
        missing.append("knowledge_artifact")
    if report is None:
        missing.append("report_artifact")
    return missing


def _records_satisfy_spec(records: list[Any], validation: dict[str, Any], spec: Any | None) -> bool:
    if not records or not validation.get("valid"):
        return False
    return _source_count_satisfied(records, spec)


def _source_count_satisfied(records: list[Any], spec: Any | None) -> bool:
    if spec is None:
        return bool(records)
    urls = {
        str(getattr(record, "source_page", "") or "").rstrip("/").lower()
        for record in records
        if getattr(record, "validation", {}).get("valid") and getattr(record, "source_page", "")
    }
    return len(urls) >= int(getattr(spec, "source_count", 1) or 1)


def _enabled() -> bool:
    return any(is_shadow_or_active(flag) for flag in ("V50_PAGE_READER", "V50_EXTRACTION_ENGINE", "V50_SYNTHESIS", "V50_REPORT_ENGINE", "V50_EXTRACTION_VALIDATION"))


def _active() -> bool:
    return any(is_active(flag) for flag in ("V50_PAGE_READER", "V50_EXTRACTION_ENGINE", "V50_SYNTHESIS", "V50_REPORT_ENGINE", "V50_EXTRACTION_VALIDATION"))


_pipeline = KnowledgeExtractionPipeline()


def observe_knowledge_pipeline(*, session_id: str, task: str, page_context: Any, current_phase: str | None = None) -> KnowledgePipelineSnapshot | None:
    return _pipeline.observe(session_id=session_id, task=task, page_context=page_context, current_phase=current_phase)


def enrich_planner_context_with_knowledge(compressed_context: dict[str, Any], snapshot: KnowledgePipelineSnapshot | None) -> dict[str, Any]:
    return _pipeline.enrich_context(compressed_context, snapshot)


def postprocess_with_knowledge(result: AnalyzeResponse, snapshot: KnowledgePipelineSnapshot | None) -> AnalyzeResponse:
    return _pipeline.postprocess_response(result, snapshot)
