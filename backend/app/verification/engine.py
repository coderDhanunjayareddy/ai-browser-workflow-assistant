from __future__ import annotations

import time
from typing import Any

from app.schemas.request import PageContext
from app.semantic_page.graph import SemanticPageGraph
from app.verification.evidence import collect_execution_evidence, collect_report_evidence
from app.verification.models import ValidationObject
from app.verification.rules import evaluate_execution_rule, evaluate_report_rule
from app.verification.telemetry import record_validation_metrics


class ValidationEngine:
    """Deterministic V3.4 validation pipeline.

    The engine evaluates observed outcomes against expected outcomes. It does
    not plan, execute, route workflow decisions, or mutate mission state.
    """

    def validate_report(
        self,
        *,
        run_id: str,
        mission_id: str,
        step_id: str,
        claim: str,
        answer: str | None,
        page_context: PageContext,
        semantic_graph: SemanticPageGraph | None = None,
    ) -> tuple[ValidationObject, int]:
        started = time.perf_counter()
        evidence_started = time.perf_counter()
        evidence = collect_report_evidence(
            page_context=page_context,
            semantic_graph=semantic_graph,
        )
        evidence_ms = int((time.perf_counter() - evidence_started) * 1000)
        status, confidence, category, observed, missing = evaluate_report_rule(
            answer=answer,
            evidence=evidence,
        )
        validation = ValidationObject(
            run_id=run_id,
            mission_id=mission_id,
            step_id=step_id,
            expected_outcome=claim or "report_supported_by_page_evidence",
            observed_outcome=answer or "",
            evidence=evidence,
            validation_status=status,
            confidence=confidence,
            failure_category=category,
            required_evidence=[answer] if answer else ["specific_report_answer"],
            observed_evidence=observed,
            missing_evidence=missing,
            replay_metadata={
                "pipeline": "report",
                "evidence_ms": evidence_ms,
                "evidence_count": len(evidence),
                "semantic_graph_id": semantic_graph.graph_id if semantic_graph else None,
            },
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_validation_metrics(run_id, validation, latency_ms=latency_ms)
        return validation, latency_ms

    def validate_execution(
        self,
        *,
        run_id: str,
        mission_id: str,
        step_id: str,
        action_type: str,
        selector: str,
        success: bool,
        execution_result: str,
        before_url: str | None = None,
        after_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ValidationObject, int]:
        started = time.perf_counter()
        evidence_started = time.perf_counter()
        evidence = collect_execution_evidence(
            action_type=action_type,
            selector=selector,
            success=success,
            execution_result=execution_result,
            before_url=before_url,
            after_url=after_url,
            metadata=metadata,
        )
        evidence_ms = int((time.perf_counter() - evidence_started) * 1000)
        status, confidence, category, observed, missing, contradictions = evaluate_execution_rule(
            action_type=action_type,
            success=success,
            execution_result=execution_result,
            before_url=before_url,
            after_url=after_url,
        )
        validation = ValidationObject(
            run_id=run_id,
            mission_id=mission_id,
            step_id=step_id,
            expected_outcome=f"{action_type}_achieved_intended_effect",
            observed_outcome=execution_result,
            evidence=evidence,
            validation_status=status,
            confidence=confidence,
            failure_category=category,
            required_evidence=["execution_success"],
            observed_evidence=observed,
            missing_evidence=missing,
            contradictions=contradictions,
            replay_metadata={
                "pipeline": "execution",
                "evidence_ms": evidence_ms,
                "evidence_count": len(evidence),
            },
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_validation_metrics(run_id, validation, latency_ms=latency_ms)
        return validation, latency_ms
