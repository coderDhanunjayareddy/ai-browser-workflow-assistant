from __future__ import annotations

from app.evaluation.models import EvaluationObject, RunScorecard
from app.observability.metrics import default_metric_sink


def record_evaluation_metrics(
    run_id: str,
    *,
    evaluation: EvaluationObject,
    scorecard: RunScorecard,
    learning_signal_count: int,
    latency_ms: int,
    scoring_ms: int,
) -> None:
    default_metric_sink.record("v3.evaluation.latency_ms", latency_ms, run_id=run_id)
    default_metric_sink.record("v3.evaluation.scoring_ms", scoring_ms, run_id=run_id)
    default_metric_sink.record("v3.evaluation.overall_score", evaluation.overall_score, run_id=run_id)
    default_metric_sink.record("v3.evaluation.confidence", evaluation.confidence, run_id=run_id)
    default_metric_sink.record(
        "v3.learning.signal_count",
        learning_signal_count,
        run_id=run_id,
    )
    default_metric_sink.record(
        "v3.scorecard.status",
        1,
        run_id=run_id,
        tags={"status": scorecard.status},
    )


def record_regression_metrics(
    run_id: str,
    *,
    comparison_count: int,
    regression_count: int,
    improved_count: int,
) -> None:
    default_metric_sink.record("v3.regression.comparison_count", comparison_count, run_id=run_id)
    default_metric_sink.record("v3.regression.regression_count", regression_count, run_id=run_id)
    default_metric_sink.record("v3.regression.improved_count", improved_count, run_id=run_id)

