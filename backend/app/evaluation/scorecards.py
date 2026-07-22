from __future__ import annotations

from app.evaluation.models import EvaluationObject, RunScorecard


def build_scorecard(evaluation: EvaluationObject) -> RunScorecard:
    status = "unknown"
    if evaluation.mission_summary.get("completed"):
        status = "succeeded"
    elif evaluation.mission_summary.get("failed"):
        status = "failed"
    elif evaluation.overall_score > 0:
        status = "partial"

    return RunScorecard(
        run_id=evaluation.run_id,
        evaluation_id=evaluation.evaluation_id,
        mission_id=evaluation.mission_id,
        status=status,  # type: ignore[arg-type]
        success=status == "succeeded",
        execution_summary=evaluation.execution_metrics.model_dump(mode="json"),
        validation_summary=evaluation.validation_summary,
        governance_summary=evaluation.governance_summary,
        timing={"total_latency_ms": evaluation.execution_metrics.total_latency_ms},
        retries=evaluation.execution_metrics.retry_count,
        confidence=evaluation.confidence,
        overall_score=evaluation.overall_score,
        regression_flags=[],
    )

