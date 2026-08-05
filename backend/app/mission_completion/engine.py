from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.feature_flags import is_active, is_shadow_or_active
from app.knowledge_extraction.models import KnowledgePipelineSnapshot
from app.mission.intelligence.mission_plan import create_mission_plan
from app.mission_completion.criteria import evaluate_success_criteria
from app.mission_completion.models import (
    CompletionDecision,
    CompletionEvidence,
    CompletionStatus,
    CriterionEvaluation,
    CriterionKind,
    MissionPlan,
    MissionCompletionSnapshot,
    SourceCoverage,
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
        mission_plan = create_mission_plan(
            mission_id=session_id,
            objective=task,
            phase_state=phase_state,
        )
        evaluations = evaluate_success_criteria(
            mission_plan=mission_plan,
            knowledge_snapshot=knowledge_snapshot,
            runtime_state=runtime_state,
            phase_state=phase_state,
        )
        evidence = _evidence(knowledge_snapshot, evaluations)
        decision, status, reason, confidence, retry_target = _decide(
            evidence=evidence,
            mission_plan=mission_plan,
            evaluations=evaluations,
            knowledge_snapshot=knowledge_snapshot,
            phase_state=phase_state,
            runtime_state=runtime_state,
        )
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
            mission_plan=mission_plan,
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
            goal_convergence=True,
            backend_authoritative_report=True,
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
        if snapshot.decision == CompletionDecision.INCOMPLETE and snapshot.retry_target != "none" and _is_wait_outcome(result):
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


def _evidence(
    snapshot: KnowledgePipelineSnapshot | None,
    evaluations: list[CriterionEvaluation] | None = None,
) -> CompletionEvidence:
    evaluations = list(evaluations or [])
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
            criteria_evaluations=evaluations,
            source_coverage=SourceCoverage(required_count=1, distinct_count=0, source_urls=[], satisfied=False, missing_count=1),
        )
    valid_records = [
        record for record in snapshot.extraction_records
        if bool(record.validation.get("valid"))
    ]
    urls = sorted({
        normalized
        for url in [*(getattr(read, "canonical_url", "") for read in snapshot.read_artifacts), *(record.source_page for record in snapshot.extraction_records)]
        for normalized in [_normalize_web_url(url)]
        if normalized
    })
    required_source_count = int(getattr(getattr(snapshot, "research_spec", None), "source_count", 1) or 1)
    coverage = SourceCoverage(
        required_count=required_source_count,
        distinct_count=len(urls),
        source_urls=urls,
        satisfied=len(urls) >= required_source_count,
        missing_count=max(required_source_count - len(urls), 0),
    )
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
        criteria_evaluations=evaluations,
        source_coverage=coverage,
    )


def _is_wait_outcome(result: AnalyzeResponse) -> bool:
    if result.outcome_kind == "wait":
        return True
    return bool(
        result.outcome_kind == "act"
        and result.suggested_actions
        and str(result.suggested_actions[0].action_type or "").lower() == "wait"
    )


def _is_web_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_web_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        ],
        doseq=True,
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, ""))


def _decide(
    *,
    evidence: CompletionEvidence,
    mission_plan: MissionPlan,
    evaluations: list[CriterionEvaluation],
    knowledge_snapshot: KnowledgePipelineSnapshot | None,
    phase_state: Any,
    runtime_state: Any,
) -> tuple[CompletionDecision, CompletionStatus, str, float, str]:
    if _budget_exhausted(phase_state):
        return CompletionDecision.FAILED, CompletionStatus.FAILED, "Execution budget exhausted before mission success criteria were satisfied.", 0.0, "none"
    if _runtime_blocked(runtime_state):
        return CompletionDecision.BLOCKED, CompletionStatus.BLOCKED, "Runtime state is inconsistent and blocks reliable completion evaluation.", 0.0, "recovery"

    blocking = [evaluation for evaluation in evaluations if _criterion(mission_plan, evaluation.criterion_id).blocking]
    missing_blocking = [evaluation for evaluation in blocking if not evaluation.satisfied]
    if blocking and not missing_blocking:
        return CompletionDecision.COMPLETE, CompletionStatus.COMPLETE, "All blocking mission success criteria are satisfied by provider evidence.", _confidence(evaluations), "none"

    approval_missing = next((evaluation for evaluation in missing_blocking if evaluation.kind == CriterionKind.APPROVAL_OBTAINED), None)
    if approval_missing is not None:
        return CompletionDecision.NEEDS_USER, CompletionStatus.NEEDS_USER, approval_missing.blocking_reason or "User approval is required.", approval_missing.confidence, "none"

    external_missing = next((evaluation for evaluation in missing_blocking if evaluation.kind == CriterionKind.EXTERNAL_CONFIRMATION_RECEIVED), None)
    if external_missing is not None:
        return CompletionDecision.WAITING_EXTERNAL, CompletionStatus.WAITING_EXTERNAL, external_missing.blocking_reason or "External confirmation is still pending.", external_missing.confidence, "none"

    if _has_partial_success(evaluations, knowledge_snapshot):
        return CompletionDecision.PARTIAL_SUCCESS, CompletionStatus.PARTIAL_SUCCESS, "Some mission success criteria are satisfied, but required evidence is incomplete.", _confidence(evaluations), "none"

    retry_target = _retry_target(missing_blocking, evidence)
    if retry_target != "none":
        reason = "; ".join(evaluation.blocking_reason or evaluation.criterion_id for evaluation in missing_blocking[:3])
        return CompletionDecision.INCOMPLETE, CompletionStatus.INCOMPLETE, reason or "Mission success criteria require more evidence.", _confidence(evaluations), retry_target

    if knowledge_snapshot is None:
        return CompletionDecision.INCOMPLETE, CompletionStatus.INCOMPLETE, "Mission evidence is still being collected.", 0.0, "none"
    return CompletionDecision.INCOMPLETE, CompletionStatus.INCOMPLETE, "Mission success criteria are not satisfied yet.", _confidence(evaluations), "none"


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


def _criterion(mission_plan: MissionPlan, criterion_id: str):
    return next((criterion for criterion in mission_plan.success_criteria if criterion.criterion_id == criterion_id), mission_plan.success_criteria[0])


def _budget_exhausted(phase_state: Any) -> bool:
    budgets = getattr(phase_state, "budgets", None)
    return bool(getattr(budgets, "exhausted", []) or [])


def _runtime_blocked(runtime_state: Any) -> bool:
    consistency = getattr(runtime_state, "consistency", None)
    return bool(consistency is not None and getattr(consistency, "valid", True) is False)


def _has_partial_success(evaluations: list[CriterionEvaluation], snapshot: KnowledgePipelineSnapshot | None) -> bool:
    if snapshot is None or snapshot.report_artifact is None:
        return False
    if snapshot.report_artifact.completion_status != "complete":
        return False
    if snapshot.research_spec is not None and not bool(snapshot.completion_status.get("source_count")):
        return False
    return any(evaluation.satisfied for evaluation in evaluations)


def _retry_target(
    missing_blocking: list[CriterionEvaluation],
    evidence: CompletionEvidence,
) -> str:
    missing_kinds = {evaluation.kind for evaluation in missing_blocking}
    if CriterionKind.REPORT_DELIVERED in missing_kinds:
        return "report"
    if CriterionKind.ARTIFACT_CREATED in missing_kinds:
        return "synthesize"
    if CriterionKind.ARTIFACT_VALIDATED in missing_kinds:
        return "validate" if evidence.extraction_record_count else "extract"
    if CriterionKind.FIELD_EXTRACTED in missing_kinds:
        return "extract" if evidence.read_count else "read"
    if CriterionKind.PAGE_READ in missing_kinds:
        return "read"
    if CriterionKind.BROWSER_STATE_REACHED in missing_kinds:
        return "recovery"
    return "none"


def _confidence(evaluations: list[CriterionEvaluation]) -> float:
    if not evaluations:
        return 0.0
    return sum(evaluation.confidence for evaluation in evaluations) / len(evaluations)


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
