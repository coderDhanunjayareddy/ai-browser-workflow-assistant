from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from app.feature_flags import is_active, is_shadow_or_active
from app.knowledge_extraction.models import KnowledgePipelineSnapshot
from app.mission_completion.models import (
    CompletionDecision,
    CompletionEvidence,
    CompletionStatus,
    MissionCompletionSnapshot,
    WorkflowResult,
)
from app.mission_completion.replay import build_replay
from app.mission_completion.telemetry import build_telemetry
from app.schemas.response import AnalyzeResponse, ReportOutcome, ReplanOutcome


class MissionCompletionController:
    def observe(
        self,
        *,
        session_id: str,
        task: str,
        knowledge_snapshot: KnowledgePipelineSnapshot | None,
        phase_state: Any = None,
        runtime_state: Any = None,
        execution_state: Any = None,
        planner_response: AnalyzeResponse | None = None,
    ) -> MissionCompletionSnapshot | None:
        if not is_shadow_or_active("V51_MISSION_COMPLETION_CONTROLLER"):
            return None
        started = time.perf_counter()
        evidence = _evidence(knowledge_snapshot)
        decision, status, reason, confidence, retry_target = _decide(evidence, knowledge_snapshot)
        workflow_result = _workflow_result(
            decision=decision,
            status=status,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            knowledge_snapshot=knowledge_snapshot,
            started=started,
            runtime_state=runtime_state,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        report_ms = knowledge_snapshot.telemetry.report_ms if knowledge_snapshot is not None else 0
        telemetry = build_telemetry(
            latency_ms=latency_ms,
            reason=reason,
            decision=decision,
            confidence=confidence,
            partial_count=1 if decision == CompletionDecision.PARTIAL_SUCCESS else 0,
            report_generation_ms=report_ms,
            planner_calls_saved=1 if workflow_result is not None and planner_response is None else 0,
        )
        replay = build_replay(
            session_id=session_id,
            decision=decision,
            reason=reason,
            evidence=evidence,
            report_artifact_id=evidence.report_artifact_id,
        )
        return MissionCompletionSnapshot(
            schema_version="mission_completion.v1",
            session_id=session_id,
            decision=decision,
            status=status,
            reason=reason,
            confidence=confidence,
            evidence=evidence,
            workflow_result=workflow_result,
            telemetry=telemetry,
            replay=replay,
            retry_target=retry_target,
        )

    def enrich_context(
        self,
        compressed_context: dict[str, Any],
        snapshot: MissionCompletionSnapshot | None,
    ) -> dict[str, Any]:
        if snapshot is None or not is_active("V51_MISSION_COMPLETION_CONTROLLER"):
            return compressed_context
        enriched = dict(compressed_context)
        enriched["mission_completion"] = snapshot.to_compact_context()
        return enriched

    def should_terminate_before_planner(self, snapshot: MissionCompletionSnapshot | None) -> bool:
        return bool(
            snapshot is not None
            and is_active("V51_MISSION_COMPLETION_CONTROLLER")
            and snapshot.workflow_result is not None
            and snapshot.decision in {CompletionDecision.COMPLETE, CompletionDecision.PARTIAL_SUCCESS, CompletionDecision.FAILED}
        )

    def completion_response(self, session_id: str, snapshot: MissionCompletionSnapshot) -> AnalyzeResponse:
        if snapshot.workflow_result is None:
            raise ValueError("Mission completion response requires a workflow result")
        report = snapshot.workflow_result.report_artifact or {}
        answer = str(report.get("content") or "")
        return AnalyzeResponse(
            session_id=session_id,
            analysis=f"Mission Completion Controller terminated the workflow: {snapshot.reason}",
            outcome_kind="report",
            clarification_question=None,
            report=ReportOutcome(answer=answer, claim=snapshot.reason),
            replan=None,
            suggested_actions=[],
            sgv_verified=snapshot.decision == CompletionDecision.COMPLETE,
            goal_convergence=False,
        )

    def postprocess_response(
        self,
        result: AnalyzeResponse,
        snapshot: MissionCompletionSnapshot | None,
    ) -> AnalyzeResponse:
        if snapshot is None or not is_active("V51_MISSION_COMPLETION_CONTROLLER"):
            return result
        if snapshot.workflow_result is not None:
            return self.completion_response(result.session_id, snapshot)
        if snapshot.decision == CompletionDecision.RETRY and result.outcome_kind == "wait":
            return AnalyzeResponse(
                session_id=result.session_id,
                analysis=f"Mission Completion Controller selected retry target: {snapshot.retry_target}",
                outcome_kind="replan",
                clarification_question=None,
                report=None,
                replan=ReplanOutcome(reason=snapshot.reason),
                suggested_actions=[],
                sgv_verified=False,
                goal_convergence=result.goal_convergence,
            )
        return result


def _evidence(snapshot: KnowledgePipelineSnapshot | None) -> CompletionEvidence:
    if snapshot is None:
        return CompletionEvidence(
            required_fields=[],
            read_count=0,
            extraction_record_count=0,
            valid_record_count=0,
            report_artifact_id=None,
            knowledge_artifact_id=None,
            missing_artifacts=["knowledge_snapshot"],
            completion_status={},
            source_urls=[],
        )
    valid_records = [
        record for record in snapshot.extraction_records
        if bool(record.validation.get("valid"))
    ]
    urls = sorted({record.source_page for record in snapshot.extraction_records if _is_web_url(record.source_page)})
    return CompletionEvidence(
        required_fields=list(snapshot.required_fields),
        read_count=len(snapshot.read_artifacts),
        extraction_record_count=len(snapshot.extraction_records),
        valid_record_count=len(valid_records),
        report_artifact_id=snapshot.report_artifact.id if snapshot.report_artifact else None,
        knowledge_artifact_id=snapshot.knowledge_artifact.id if snapshot.knowledge_artifact else None,
        missing_artifacts=list(snapshot.missing_artifacts),
        completion_status=dict(snapshot.completion_status),
        source_urls=urls,
    )


def _is_web_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _decide(
    evidence: CompletionEvidence,
    snapshot: KnowledgePipelineSnapshot | None,
) -> tuple[CompletionDecision, CompletionStatus, str, float, str]:
    if snapshot is None:
        return CompletionDecision.CONTINUE, CompletionStatus.RUNNING, "Knowledge extraction has not produced evidence yet.", 0.0, "none"
    report_ready = bool(snapshot.report_artifact and snapshot.report_artifact.completion_status == "complete")
    validated = bool(snapshot.completion_status.get("extract"))
    has_records = evidence.extraction_record_count > 0
    has_valid_records = evidence.valid_record_count > 0
    has_valid_sources = bool(evidence.source_urls)
    if report_ready and validated and not evidence.missing_artifacts:
        return CompletionDecision.COMPLETE, CompletionStatus.COMPLETE, "Validated report artifact satisfies mission completion criteria.", 0.97, "none"
    if report_ready and has_valid_records and has_valid_sources:
        return CompletionDecision.PARTIAL_SUCCESS, CompletionStatus.PARTIAL_SUCCESS, "Report artifact exists with partial validated evidence.", 0.78, "none"
    if has_records and not report_ready:
        return CompletionDecision.RETRY, CompletionStatus.RUNNING, "Extracted records exist but final report artifact is missing.", 0.62, "report"
    if has_records and not has_valid_records:
        return CompletionDecision.RETRY, CompletionStatus.RUNNING, "Extraction records exist but none are valid completion evidence.", 0.46, "extract"
    if evidence.read_count and not has_records:
        return CompletionDecision.RETRY, CompletionStatus.RUNNING, "Readable page evidence exists but extraction records are missing.", 0.52, "extract"
    return CompletionDecision.CONTINUE, CompletionStatus.RUNNING, "Mission evidence is still being collected.", 0.35, "none"


def _workflow_result(
    *,
    decision: CompletionDecision,
    status: CompletionStatus,
    reason: str,
    confidence: float,
    evidence: CompletionEvidence,
    knowledge_snapshot: KnowledgePipelineSnapshot | None,
    started: float,
    runtime_state: Any,
) -> WorkflowResult | None:
    if decision not in {CompletionDecision.COMPLETE, CompletionDecision.PARTIAL_SUCCESS, CompletionDecision.FAILED}:
        return None
    report = knowledge_snapshot.report_artifact.to_dict() if knowledge_snapshot and knowledge_snapshot.report_artifact else None
    metrics = {
        "read_count": evidence.read_count,
        "extraction_record_count": evidence.extraction_record_count,
        "valid_record_count": evidence.valid_record_count,
        "missing_artifact_count": len(evidence.missing_artifacts),
    }
    if knowledge_snapshot is not None:
        metrics.update(knowledge_snapshot.telemetry.to_dict())
    return WorkflowResult(
        mission_status=status.value,
        completion_reason=reason,
        report_artifact=report,
        replay_reference=f"mission_completion:{knowledge_snapshot.session_id}" if knowledge_snapshot else None,
        metrics=metrics,
        evidence_summary=evidence.to_dict(),
        duration_ms=int((time.perf_counter() - started) * 1000),
        resource_usage={
            "tabs": len(getattr(runtime_state, "tabs", []) or []),
            "artifacts": len(getattr(runtime_state, "artifacts", []) or []),
        },
        confidence=confidence,
    )


def observe_mission_completion(
    *,
    session_id: str,
    task: str,
    knowledge_snapshot: KnowledgePipelineSnapshot | None,
    phase_state: Any = None,
    runtime_state: Any = None,
    execution_state: Any = None,
    planner_response: AnalyzeResponse | None = None,
) -> MissionCompletionSnapshot | None:
    return _controller.observe(
        session_id=session_id,
        task=task,
        knowledge_snapshot=knowledge_snapshot,
        phase_state=phase_state,
        runtime_state=runtime_state,
        execution_state=execution_state,
        planner_response=planner_response,
    )


def enrich_planner_context_with_completion(
    compressed_context: dict[str, Any],
    snapshot: MissionCompletionSnapshot | None,
) -> dict[str, Any]:
    return _controller.enrich_context(compressed_context, snapshot)


def should_terminate_before_planner(snapshot: MissionCompletionSnapshot | None) -> bool:
    return _controller.should_terminate_before_planner(snapshot)


def completion_response(session_id: str, snapshot: MissionCompletionSnapshot) -> AnalyzeResponse:
    return _controller.completion_response(session_id, snapshot)


def postprocess_with_mission_completion(
    result: AnalyzeResponse,
    snapshot: MissionCompletionSnapshot | None,
) -> AnalyzeResponse:
    return _controller.postprocess_response(result, snapshot)


_controller = MissionCompletionController()
