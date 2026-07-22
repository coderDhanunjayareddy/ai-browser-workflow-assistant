from __future__ import annotations

from pydantic import BaseModel, Field

from app.evaluation.models import EvaluationObject
from app.evaluation.telemetry import record_regression_metrics


class RegressionResult(BaseModel):
    source_evaluation_id: str
    candidate_evaluation_id: str
    score_delta: float
    latency_delta_ms: int
    retry_delta: int
    regression_flags: list[str] = Field(default_factory=list)
    improvement_flags: list[str] = Field(default_factory=list)


def compare_evaluations(
    *,
    baseline: EvaluationObject,
    candidate: EvaluationObject,
) -> RegressionResult:
    score_delta = round(candidate.overall_score - baseline.overall_score, 4)
    latency_delta = (
        candidate.execution_metrics.total_latency_ms
        - baseline.execution_metrics.total_latency_ms
    )
    retry_delta = (
        candidate.execution_metrics.retry_count
        - baseline.execution_metrics.retry_count
    )
    regressions: list[str] = []
    improvements: list[str] = []

    if score_delta <= -0.05:
        regressions.append("overall_score_regressed")
    elif score_delta >= 0.05:
        improvements.append("overall_score_improved")
    if retry_delta > 0:
        regressions.append("retry_count_increased")
    elif retry_delta < 0:
        improvements.append("retry_count_decreased")
    if latency_delta > 1000:
        regressions.append("latency_increased")
    elif latency_delta < -1000:
        improvements.append("latency_decreased")

    result = RegressionResult(
        source_evaluation_id=baseline.evaluation_id,
        candidate_evaluation_id=candidate.evaluation_id,
        score_delta=score_delta,
        latency_delta_ms=latency_delta,
        retry_delta=retry_delta,
        regression_flags=regressions,
        improvement_flags=improvements,
    )
    record_regression_metrics(
        candidate.run_id,
        comparison_count=1,
        regression_count=len(regressions),
        improved_count=len(improvements),
    )
    return result

